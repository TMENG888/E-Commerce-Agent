import asyncio
import os
import random
from urllib.parse import urlparse, parse_qs  # 用于解析 URL

from playwright.async_api import async_playwright

from anti_detect import (
    STEALTH_JS, HumanMouse, human_scroll, human_delay,
    rate_limiter
)
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

    async def download_image(self, page, url, index):
        """[修改] 使用浏览器上下文下载"""
        try:
            clean_url = url.split('?')[0]
            if not clean_url.startswith('http'): clean_url = 'https:' + clean_url
            response = await page.request.get(clean_url)
            if response.ok:
                content = await response.body()
                file_path = os.path.join(self.save_root, f"review_{index}.jpg")
                with open(file_path, 'wb') as f:
                    f.write(content)
        except Exception as e:
            print(f"❌ 图片下载失败: {e}")

    async def run(self, url):
        await self.clear_folder(self.save_root)
        
        async with async_playwright() as p:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]
            
            # [修改] 注入反检测脚本
            await context.add_init_script(STEALTH_JS)
            
            all_pages = context.pages
            page = None
            for p in all_pages:
                if p.url == url:
                    page = p
                    break
            
            if not page:
                print("❌ 未找到目标页面")
                return

            HumanMouse(page)
            # [修改4] 人性化滚动加载详情图
            print("📜 正在向下滚动以触发详情图加载...")
            for _ in range(random.randint(6, 9)):  # 随机次数
                await human_scroll(page, 'up', random.randint(1000, 2500))
                await human_delay(0.8, 2.5)  # 随机间隔

            # [关键修改] 不再用 evaluate("el.click()")，改为 HumanMouse 点击
            await page.locator('span.IpR_6z4r', has_text="查看全部").click()
            await human_delay(1.5, 3)
            
            # [修改] 点击"有图"筛选
            await page.locator('li.tmdcnU0p', has_text="图/视频").click()
            await human_delay(0.8, 2)

            # [优化版] 人性化智能滚动
            print("📜 开始智能滚动加载...")
            last_height = await page.evaluate("document.body.scrollHeight")
            last_count = 0
            no_new_count = 0

            for i in range(MAX_SCROLL_TIMES):
                # 混合检测：统计图片数量 + 当前页面高度
                current_imgs = await page.locator('img.pdd-lazy-image[data-src*="review"]').count()
                current_height = await page.evaluate("document.body.scrollHeight")

                # 只要图片变多了，或者页面长高了，都算有新内容
                if current_imgs > last_count or current_height > last_height:
                    print(f"✅ 发现新内容：图片({current_imgs}), 高度({current_height})")
                    last_count = current_imgs
                    last_height = current_height
                    no_new_count = 0
                else:
                    no_new_count += 1
                    print(f"⏳ 连续 {no_new_count} 次未发现新内容，尝试深度等待...")
                    # 如果第一次没发现，先多等两秒，防止网络抖动
                    await asyncio.sleep(2)

                if no_new_count >= 3:
                    # 【终极补救】在确定退出前，尝试大跨度滚动一次，看看能不能触发加载
                    print("🔍 尝试最后一次大跨度滚动...")
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(3)
                    final_height = await page.evaluate("document.body.scrollHeight")
                    if final_height > last_height:
                        no_new_count = 0  # 重置，继续滚
                        continue
                    else:
                        print("⏹️ 确定彻底无新内容，退出滚动")
                        break

                # 模拟人类行为滚动
                scroll_dist = random.randint(1500, 3500)
                await human_scroll(page, 'down', scroll_dist)
                await human_delay(1.5, 3.0)  # 稍微增加等待时间，给数据渲染留余地

            # 采集与下载
            img_urls = set()
            images = await page.locator('img.pdd-lazy-image[data-src*="review"]').all()
            for img in images:
                src = await img.get_attribute("data-src") or await img.get_attribute("src")
                if src: img_urls.add(src.split('?')[0])
            
            print(f"📸 最终锁定 {len(img_urls)} 张评价图")
            
            # [修改] 串行下载（不再并行）
            for i, url in enumerate(img_urls):
                await rate_limiter.wait_if_needed('image_download')
                await self.download_image(page, url, i)
                await human_delay(0.3, 1.5)
            
            print(f"\n🏁 完成！存放位置: {self.save_root}")


if __name__ == "__main__":
    # 现在只需要传入基础目录和目标 URL，goods_id 会自动识别
    downloader = PddReviewDownloader(BASE_SAVE_DIR, TARGET_URL)
    asyncio.run(downloader.run(TARGET_URL))