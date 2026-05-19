import os
import asyncio
import re
import requests
from urllib.parse import urlparse, parse_qs  # 用于解析 URL
from playwright.async_api import async_playwright
from base import Base

base = Base()

# --- 核心配置 ---
BASE_SAVE_DIR = r"C:\Users\31193\Pictures\商品实拍图"
MAX_SCROLL_TIMES = 20  # 调高上限，由逻辑判断提前停止
TARGET_URL = "https://mobile.pinduoduo.com/goods.html?goods_id=917605357155&_oak_rcto=YWI_IV-Vh5fY8xZDHDfXF9mu9F_WhvZ96bbf9sz4gxd1-t39KSoAd3QX&_oc_trace_mark=199&_oc_adinfo=eyJwYWdlX3NuIjoxMDAyOCwic2NlbmVfaWQiOjR9&_oak_gallery_token=6d48197a95d0644b53e06d7d82f3fcde&_oak_gallery=https%3A%2F%2Fimg.pddpic.com%2Fopen-gw%2F2026-03-12%2F8522a8d7-111c-40b1-a1d9-5c44950efce6.jpeg&_oc_refer_ad=1&page_from=205&thumb_url=https%3A%2F%2Fimg.pddpic.com%2Fopen-gw%2F2026-03-12%2F8522a8d7-111c-40b1-a1d9-5c44950efce6.jpeg%3FimageMogr2%2Fthumbnail%2F400x%257CimageView2%2F2%2Fw%2F400%2Fq%2F80&refer_page_name=opt&refer_page_id=10028_1775895605067_i6i22cgcks&refer_page_sn=10028&uin=QRKHP76NUB2ORTNS5N6GPL7EJI_GEXDA&page_id=10014_1775901289402_h5xobux34t&is_back=1"
CHROME_DEBUG_PORT = 9222


class PddReviewDownloader:
    def __init__(self, base_root, url):
        # --- 优化项 1: 自动解析 goods_id ---
        self.goods_id = self._extract_goods_id(url)
        # 路径直接以 goods_id 命名，无需手动指定关键词
        self.save_root = os.path.join(base_root, self.goods_id)

        if not os.path.exists(self.save_root):
            os.makedirs(self.save_root)
            print(f"📁 目录已根据 goods_id 准备: {self.save_root}")

    def _extract_goods_id(self, url):
        """从 URL 中精准提取 goods_id"""
        query = urlparse(url).query
        params = parse_qs(query)
        # 获取 goods_id，如果没有则返回 'unknown'
        return params.get('goods_id', ['unknown'])[0]

    async def clear_folder(self, folder_path):
        """清理历史采集文件"""
        if os.path.exists(folder_path):
            for file_name in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file_name)
                try:
                    if os.path.isfile(file_path): os.unlink(file_path)
                except:
                    pass

    async def download_image(self, url, index):
        """下载高清图"""
        try:
            clean_url = url.split('?')[0]
            if not clean_url.startswith('http'): clean_url = 'https:' + clean_url
            response = await asyncio.to_thread(requests.get, clean_url, timeout=10)
            if response.status_code == 200:
                file_path = os.path.join(self.save_root, f"review_{index}.jpg")
                with open(file_path, 'wb') as f:
                    f.write(response.content)
        except:
            pass

    async def run(self, url):
        await self.clear_folder(self.save_root)

        async with async_playwright() as p:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]

            all_pages = context.pages
            for p in all_pages:
                if p.url == url:
                    page = p
                    break

            # 进入评价页
            await page.locator('span.IpR_6z4r:has-text("查看全部")').evaluate("el => el.click()")
            await asyncio.sleep(2)

            # 点击“有图”筛选
            with_img_tab = page.get_by_text(re.compile(r"图/视频"))
            if await with_img_tab.count() > 0:
                await with_img_tab.first.click()
                await asyncio.sleep(1)

            # --- 优化项 2: 智能探测滚动逻辑 ---
            print("📜 开始智能滚动加载...")
            last_count = 0
            no_new_count = 0  # 连续未更新次数计数器

            for i in range(MAX_SCROLL_TIMES):
                # 记录滚动前图片数量
                current_imgs = await page.locator('img.pdd-lazy-image[data-src*="review"]').count()

                if current_imgs > last_count:
                    last_count = current_imgs
                    no_new_count = 0  # 重置计数器
                else:
                    no_new_count += 1
                    print(f"⏳ 连续 {no_new_count} 次尝试未发现新内容...")

                # 智能停止：如果尝试 3 次滚动都没有新图，说明到底了
                if no_new_count >= 3:
                    print("⏹️ 确定已无更多评论加载，停止滚动。")
                    break

                # 执行滚动
                await page.mouse.wheel(0, 5000)
                await asyncio.sleep(1.5)  # 留给网络请求一点时间

            # --- 采集与下载 ---
            img_urls = set()
            images = await page.locator('img.pdd-lazy-image[data-src*="review"]').all()
            for img in images:
                src = await img.get_attribute("data-src") or await img.get_attribute("src")
                if src: img_urls.add(src.split('?')[0])

            print(f"📸 最终锁定 {len(img_urls)} 张评价图，开始下载...")
            tasks = [self.download_image(url, i) for i, url in enumerate(img_urls)]
            print(f"📸 待下载图片总数：{len(tasks)} 张")
            await asyncio.gather(*tasks)

            print(f"\n🏁 完成！存放位置: {self.save_root}")


if __name__ == "__main__":
    # 现在只需要传入基础目录和目标 URL，goods_id 会自动识别
    downloader = PddReviewDownloader(BASE_SAVE_DIR, TARGET_URL)
    asyncio.run(downloader.run(TARGET_URL))