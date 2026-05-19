import os
import asyncio
import random

import requests
import re
from playwright.async_api import async_playwright
from base import Base

base = Base()

# --- 配置 ---
TARGET_URL = "https://mobile.pinduoduo.com/goods.html?goods_id=590840314505&_oak_rcto=YWJwq_BeSfMzWm3fkHbrGRi79F_WhvZ96bbf9sz4gxd1-no_1idkeeia5mJFhgOBEvBeZKhHxbnw5g&_oc_trace_mark=199&_oc_adinfo=eyJwYWdlX3NuIjoxMDAwMiwic2NlbmVfaWQiOjF9&_oak_gallery_token=f62641ba8a140618bfd021ee7f44aac0&_oak_gallery=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2024-02-28%2Fd55e828e-1bd5-4b9f-9a11-0336ad19cc2e.jpeg&_oc_refer_ad=1&page_from=24&thumb_url=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2024-02-28%2Fd55e828e-1bd5-4b9f-9a11-0336ad19cc2e.jpeg%3FimageMogr2%2Fthumbnail%2F400x%257CimageView2%2F2%2Fw%2F400%2Fq%2F80%2Fformat%2Fwebp&refer_page_name=index&refer_page_id=10002_1773482380204_1ivqf1rd5u&refer_page_sn=10002&uin=QRKHP76NUB2ORTNS5N6GPL7EJI_GEXDA"
CHROME_DEBUG_PORT = 9222


class PddGoodsDetailDownloader:
    def __init__(self, base_root):
        self.goods_root = base_root
    def get_goods_id(self, url):
        """从URL中解析goods_id"""
        match = re.search(r'goods_id=(\d+)', url)
        return match.group(1) if match else None

    async def simulate_human_browse(self, page):
        # 1. 动态获取页面上所有的菜单项文本
        # 这样可以避免手动维护 info 列表，且更符合真实页面的 DOM 结构
        top_items = await page.locator(".top-menu-item .title").all_inner_texts()
        middle_items = await page.locator(".middle-menu-item .title").all_inner_texts()
        bottom_items = await page.locator(".bottom-menu-item .title").all_inner_texts()

        # 合并所有可点击的选项
        all_options = [
            {"type": "top", "items": top_items, "selector": ".top-menu-item"},
            {"type": "middle", "items": middle_items, "selector": ".middle-menu-item"},
            {"type": "bottom", "items": bottom_items, "selector": ".bottom-menu-item"}
        ]

        # 执行 3 到 5 次随机点击规避反爬
        browse_times = random.randint(3, 5)
        print(f"开始模拟随机浏览，共 {browse_times} 次操作...")

        for i in range(browse_times):
            # 2. 随机选择一个区域 (Top/Middle/Bottom)
            category = random.choice(all_options)

            if not category["items"]:
                continue

            # 3. 随机选择该区域下的一个具体业务项
            target_text = random.choice(category["items"])
            target_selector = f"{category['selector']} >> text='{target_text}'"

            print(f"[{i + 1}/{browse_times}] 正在随机访问: {target_text}")

            try:
                # 执行点击
                await page.locator(target_selector).click()

                # 随机等待：模拟人类阅读/加载页面的时间
                await asyncio.sleep(random.uniform(2.0, 4.5))

                # 4. 随机决定如何回退（模拟真实操作习惯）
                # 有时直接回退，有时先模拟滚动一下再回退
                if random.random() > 0.5:
                    await page.mouse.wheel(0, random.randint(300, 600))
                    await asyncio.sleep(random.uniform(1, 2))

                # 执行回退回到个人中心页
                await page.go_back()

                # 回退后的缓冲等待，防止操作过快被识别
                await asyncio.sleep(random.uniform(1.5, 3.0))

            except Exception as e:
                print(f"点击 {target_text} 失败或无法回退: {e}")
                # 如果进入了无法回退的页面，重新跳转回个人中心
                await page.goto("https://mobile.pinduoduo.com/personal.html")
                await asyncio.sleep(2)

        print("✅ 随机浏览路径模拟完成")

    async def pdd_collection_workflow(self, playwright, index):
        proxies = base.get_proxy_pool()
        current_proxy = random.choice(proxies)
        # 1. 连接到已经打开的浏览器
        base.cleanup_profile()
        base.ensure_chrome_running()
        browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        context = browser.contexts[0]
        page = await context.new_page()
        await page.add_init_script(path=r'/stealth.min.js')

        try:
            # --- 第一步：访问首页 ---
            print("正在访问拼多多移动端首页...")
            await page.goto("https://mobile.pinduoduo.com/")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # --- 第二步：点击个人中心 ---
            # 使用包含“个人中心”文本的元素进行定位
            print("尝试进入个人中心...")
            personal_center = page.locator(".footer-item", has_text="个人中心")
            box = await personal_center.bounding_box()
            await page.mouse.click(box['x'] + random.randint(5, 15), box['y'] + random.randint(5, 10))
            await page.wait_for_timeout(1500)

            # # 随机点击，防止路径单一被识别
            # await self.simulate_human_browse(page)

            # --- 第三步：点击商品收藏 ---
            # 进入商品收藏页，采集商品数据
            print("进入商品收藏列表...")
            fav_goods = page.locator(".middle-menu-item", has_text="商品收藏")
            await fav_goods.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

            # --- 第四步：根据索引点击商品 ---
            product_selector = ".nbYqTNZ_"
            # 等待至少一个商品卡片出现
            await page.wait_for_selector(product_selector, timeout=5000)

            products = page.locator(product_selector)
            count = await products.count()

            if index < 1 or index > count:
                print(f"输入索引 {index} 超出范围，当前收藏夹共有 {count} 个商品。")
                return

            print(f"正在定位第 {index} 个商品...")
            target_product = products.nth(index - 1)

            # 模拟真实点击：先滚动到视口，悬停，再点击
            await target_product.scroll_into_view_if_needed()
            await target_product.hover()
            await asyncio.sleep(0.5)

            # 点击商品标题进入详情页
            await target_product.locator(".h7J5pYhu").click()
            print(f"成功进入第 {index} 个商品的详情页！")

            # 可以在这里继续你的采集逻辑...
            await page.wait_for_timeout(3000)

            return page
        except Exception as e:
            print(f"执行过程中发生错误: {e}")

    async def download_image(self, url, prefix, index, base_root, sub_folder_name):
        """异步下载图片并去重去参"""
        try:
            self.save_root = os.path.join(base_root, sub_folder_name)
            if not os.path.exists(self.save_root):
                os.makedirs(self.save_root)
                print(f"📁 目录已准备: {self.save_root}")

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
        except Exception as e:
            print(f"❌ 下载异常 {url}: {e}")

    async def run(self, index):
        async with async_playwright() as p:
            page = await self.pdd_collection_workflow(p, index)

            # 自动化参数解析
            goods_id = self.get_goods_id(page.url)
            if not goods_id:
                print("❌ URL无效，未找到goods_id")
                return

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
                img_tasks.append(self.download_image(u, "goods_image", i, self.goods_root, goods_id))

            if img_tasks:
                await asyncio.gather(*img_tasks)
            else:
                print("⚠️ 未发现可下载的图片，请检查页面是否加载完整")

            print(f"\n🏁 任务完成！所有图片存放在: {self.save_root}")

            return goods_id, page.url
