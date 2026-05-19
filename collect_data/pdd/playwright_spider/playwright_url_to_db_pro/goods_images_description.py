import os
import asyncio
import requests
import re
from playwright.async_api import async_playwright
from base import Base

base = Base()

# --- 配置 ---
TARGET_URL = "https://mobile.pinduoduo.com/goods.html?goods_id=590840314505&_oak_rcto=YWJwq_BeSfMzWm3fkHbrGRi79F_WhvZ96bbf9sz4gxd1-no_1idkeeia5mJFhgOBEvBeZKhHxbnw5g&_oc_trace_mark=199&_oc_adinfo=eyJwYWdlX3NuIjoxMDAwMiwic2NlbmVfaWQiOjF9&_oak_gallery_token=f62641ba8a140618bfd021ee7f44aac0&_oak_gallery=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2024-02-28%2Fd55e828e-1bd5-4b9f-9a11-0336ad19cc2e.jpeg&_oc_refer_ad=1&page_from=24&thumb_url=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2024-02-28%2Fd55e828e-1bd5-4b9f-9a11-0336ad19cc2e.jpeg%3FimageMogr2%2Fthumbnail%2F400x%257CimageView2%2F2%2Fw%2F400%2Fq%2F80%2Fformat%2Fwebp&refer_page_name=index&refer_page_id=10002_1773482380204_1ivqf1rd5u&refer_page_sn=10002&uin=QRKHP76NUB2ORTNS5N6GPL7EJI_GEXDA"
CHROME_DEBUG_PORT = 9222


class PddGoodsDetailDownloader:
    def __init__(self, base_root, sub_folder_name):
        self.save_root = os.path.join(base_root, sub_folder_name)
        if not os.path.exists(self.save_root):
            os.makedirs(self.save_root)
            print(f"📁 目录已准备: {self.save_root}")

    async def download_image(self, url, prefix, index):
        """异步下载图片并去重去参"""
        try:
            # 移除 URL 中的样式参数获取高清原图
            clean_url = url.split('?')[0]
            if not clean_url.startswith('http'):
                clean_url = 'https:' + clean_url

            response = await asyncio.to_thread(requests.get, clean_url, timeout=10)
            if response.status_code == 200:
                file_name = f"{prefix}_{index}.jpg"
                file_path = os.path.join(self.save_root, file_name)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ 已保存: {file_name}")
        except Exception as e:
            print(f"❌ 下载异常 {url}: {e}")

    async def run(self, url):
        async with async_playwright() as p:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]
            page = await context.new_page()

            print(f"🚀 正在打开页面并扫描图片...")
            await page.goto(url, wait_until="domcontentloaded")

            # --- 滚动逻辑：详情图通常需要向下滚动才会触发加载 ---
            print("📜 正在向下滚动以触发详情图加载...")
            for _ in range(5):  # 模拟滚动 5 次
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)

            # --- 采集逻辑 ---
            # 1. 采集轮播大图 (aria-label="商品大图")
            banner_imgs = await page.locator('img[aria-label="商品大图"]').all()
            # 2. 采集详情图 (aria-label="查看图片")
            detail_imgs = await page.locator('img[aria-label="查看图片"], img[aria-label="点击查看大图"]').all()

            img_tasks = []

            # 处理轮播图
            images_urls = set()
            for img in banner_imgs:
                src = await img.get_attribute("data-src") or await img.get_attribute("src")
                if src: images_urls.add(src)

            # 处理详情图
            for img in detail_imgs:
                src = await img.get_attribute("data-src") or await img.get_attribute("src")
                if src: images_urls.add(src)

            print(f"📊 统计：发现商品图 {len(images_urls)} 张")

            # 构建下载任务
            for i, u in enumerate(images_urls):
                img_tasks.append(self.download_image(u, "goods_image", i))

            if img_tasks:
                await asyncio.gather(*img_tasks)
            else:
                print("⚠️ 未发现可下载的图片，请检查页面是否加载完整")

            print(f"\n🏁 任务完成！所有图片存放在: {self.save_root}")