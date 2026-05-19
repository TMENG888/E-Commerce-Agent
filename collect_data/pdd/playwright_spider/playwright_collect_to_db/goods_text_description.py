import asyncio
import os

import httpx
import pymysql
from playwright.async_api import async_playwright
from base import Base

# --- 配置 ---
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

TARGET_URL = "https://mobile.pinduoduo.com/goods.html?goods_id=787183244273&_oak_rcto=YWIjRTslYKz89q393ZWzJNQfo6t7J_P9Jyzf9sz4gxd1-n01FP-_Z4WY8zjsMzE7nli-oRl2PdKiew&_oc_trace_mark=199&_oc_adinfo=eyJwYWdlX3NuIjoxMDAwMiwic2NlbmVfaWQiOjF9&_oak_gallery_token=2c3b6c395ae04a570d5c1a7de6987d40&_oak_gallery=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2025-07-08%2Fbb82d406-3197-4e77-8149-81cc4a499d00.png.a.jpeg&_oc_refer_ad=1&page_from=24&thumb_url=https%3A%2F%2Fimg.pddpic.com%2Fmms-material-img%2F2025-07-08%2Fbb82d406-3197-4e77-8149-81cc4a499d00.png.a.jpeg%3FimageMogr2%2Fthumbnail%2F400x%257CimageView2%2F2%2Fw%2F400%2Fq%2F80%2Fformat%2Fwebp&refer_page_name=index&refer_page_id=10002_1776043909597_eryfdw9q60&refer_page_sn=10002&uin=SMQMT5GWAYMLC4SNSTJXZ37LXI_GEXDA"
CHROME_DEBUG_PORT = 9222

base = Base()


class PddFullTextCollector:
    async def collect_sku_combinations(self, page, target_keys, goods_id):
        base_img_path = rf"C:\Users\31193\Pictures\商品规格图\{goods_id}"
        if not os.path.exists(base_img_path):
            os.makedirs(base_img_path)

        results = []
        spec_containers = [page.locator(f"div.bIhLWVqm:has(span.sku-specs-key:text-is('{key}'))") for key in
                           target_keys]
        all_options = [c.locator('div[role="button"]') for c in spec_containers]

        async def download_image(url, file_name):
            """异步下载图片"""
            valid_name = "".join([c for c in file_name if c not in r'\/:*?"<>|']).strip()
            save_full_path = os.path.join(base_img_path, f"{valid_name}.jpg")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=10)
                    if resp.status_code == 200:
                        with open(save_full_path, 'wb') as f:
                            f.write(resp.content)
            except Exception as e:
                print(f"❌ 图片下载失败 {url}: {e}")

        async def traverse(index, current_names):
            # --- 终止条件：采集价格 ---
            if index == len(all_options):
                price_locator = page.locator('div.kYzukoxf div.ujEqGzEB')
                full_price = await price_locator.inner_text() if await price_locator.count() > 0 else "N/A"
                results.append(f"{' + '.join(current_names)} (￥{full_price.replace('¥', '').strip()})")

                sku_name = " + ".join(current_names)

                img_element = page.locator('div.O7pEFvHR img').first
                img_url = await img_element.get_attribute('src')
                if img_url:
                    # 处理拼多多图片链接（去掉末尾的 webp 处理参数，获取更清晰的图）
                    clean_url = img_url.split('?')[0] if '?' in img_url else img_url
                    # 异步下载，不阻塞遍历
                    await download_image(clean_url, sku_name)
                return

            count = await all_options[index].count()
            last_clicked_opt = None  # 记录本层最后一次成功点击的元素

            for i in range(count):
                opt = all_options[index].nth(i)
                class_attr = await opt.get_attribute("class") or ""

                # 1. 自动跳过失效 SKU
                if "uRVpnTQ1" in class_attr:
                    continue

                name = (await opt.get_attribute("aria-label") or await opt.inner_text()).strip()

                # 2. 点击切换状态
                # 只要没被选中就点击（即使是最高层也需要点击切换）
                if "hr353bdX" not in class_attr:
                    await opt.click()
                    await asyncio.sleep(0.4)  # 等待联动刷新

                last_clicked_opt = opt  # 更新本层最后操作的元素

                # 3. 递归进入下一层
                await traverse(index + 1, current_names + [name])

            # --- 核心优化点：层级回溯清理 ---
            # 只有 index > 0 (非最高层) 且 本层有过点击行为时，才在循环结束后进行一次反选
            if index > 0 and last_clicked_opt is not None:
                current_class_after = await last_clicked_opt.get_attribute("class") or ""
                if "hr353bdX" in current_class_after:
                    await last_clicked_opt.click()
                    await asyncio.sleep(0.3)
                    print(f"🧹 本层遍历结束，清理低层状态: {current_names[-1] if current_names else 'Root'}")

        await traverse(0, [])
        return results

    async def run(self, url):
        target_keyword = "https://mobile.pinduoduo.com/goods_comments.html"
        async with async_playwright() as p:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]

            all_pages = context.pages
            for p in all_pages:
                if target_keyword in p.url:
                    page = p
                    break

            await page.go_back(wait_until="domcontentloaded")

            # --- 1. 提取 goods_id ---
            goods_id = url.split("goods_id=")[-1].split("&")[0]

            # --- 2. 提取商品标题 ---
            title_selector = 'div.A6m4Y9EB.nFFS4Eh4 span.tLYIg_Ju'
            title_text = ""
            if await page.locator(title_selector).count() > 0:
                title_text = (await page.locator(title_selector).first.inner_text()).strip()
                print(f"🎯 标题提取成功: {title_text}")

            # --- 3. 提取商品参数 (详情页内) ---
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1)
            expand_btn = page.locator('div[role="button"]:has-text("查看全部")')
            if await expand_btn.count() > 0 and await expand_btn.is_visible():
                await expand_btn.click()
                await asyncio.sleep(0.8)

            params_list = []
            # 兼容弹窗和页面主体两种类名
            param_selectors = [('div.RY5AHn6B', '.ZamFNzqv', '.U2H_DQlj'), ('div.iUUH2sOQ', '.rMnkPxwx', '.KjtdjVU2')]
            for container, k_cls, v_cls in param_selectors:
                items = page.locator(container)
                if await items.count() > 0:
                    for i in range(await items.count()):
                        item = items.nth(i)
                        k = await item.locator(k_cls).inner_text()
                        v = await item.locator(v_cls).inner_text()
                        params_list.append(f"{k.strip()}：{v.strip()}")
                    break

            # --- 4. 唤起 SKU 面板 ---
            sku_trigger = page.locator('div.AANc1tSj div[role="button"]').last
            sku_price_data = []
            if await sku_trigger.count() > 0:
                await sku_trigger.click()
                await asyncio.sleep(1)

                # 定位所有的规格标题元素，例如：颜色、版本
                spec_key_locators = page.locator('span.sku-specs-key')
                auto_specs = await spec_key_locators.all_inner_texts()

                # 过滤掉空字符串，得到最终的规格列表，例如 ['颜色', '版本']
                spec_input = [s.strip() for s in auto_specs if s.strip()]
                print(f"检测到规格维度: {spec_input}")

                if spec_input:
                    # 3. 核心：采集组合价格（直接传入自动获取到的 spec_input）
                    sku_price_data = await self.collect_sku_combinations(page, spec_input, goods_id)
                else:
                    print("⚠️ 未能在面板中找到规格维度名称")

                # 关闭面板
                await page.mouse.click(10, 10)

            # 4. 拼接最终描述
            sku_desc = " | ".join(sku_price_data)

            # --- 5. 拼接最终描述 ---
            final_desc = (
                f"【商品标题】：{title_text}\n"
                f"【SKU价格详情】：{sku_desc}\n"
                f"【详细参数】：{' | '.join(params_list) if params_list else '暂无参数'}"
            )

            # --- 6. 存储到数据库 ---
            self.save_to_db(goods_id, final_desc)

            print("🏁 任务完成")

    def save_to_db(self, goods_id, text_desc):
        try:
            conn = pymysql.connect(**MYSQL_CONFIG)
            with conn.cursor() as cursor:
                sql = "INSERT INTO goods_descriptions (goods_id, text_desc) VALUES (%s, %s) ON DUPLICATE KEY UPDATE text_desc = VALUES(text_desc)"
                cursor.execute(sql, (goods_id, text_desc))
            print(f"✅ 数据已同步: ID={goods_id}")
        except Exception as e:
            print(f"❌ 存储失败: {e}")
        finally:
            if 'conn' in locals(): conn.close()


if __name__ == "__main__":
    collector = PddFullTextCollector()
    asyncio.run(collector.run(TARGET_URL))