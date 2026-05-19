import asyncio
import os
import random

import pymysql
from playwright.async_api import async_playwright

from anti_detect import (
    STEALTH_JS, HumanMouse, human_scroll, human_delay,
    rate_limiter
)
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
        """SKU组合采集 — 核心优化：人性化点击间隔"""
        base_img_path = rf"C:\Users\31193\Pictures\商品规格图\{goods_id}"
        if not os.path.exists(base_img_path):
            os.makedirs(base_img_path)
        
        mouse = HumanMouse(page)  # [修改] 使用人性化鼠标
        results = []
        spec_containers = [page.locator(f"div.bIhLWVqm:has(span.sku-specs-key:text-is('{key}'))") for key in target_keys]
        all_options = [c.locator('div[role="button"]') for c in spec_containers]
        
        async def download_image(page, url, file_name):
            """[修改] 使用浏览器上下文下载"""
            valid_name = "".join([c for c in file_name if c not in r'\/:*?"<>|']).strip()
            save_full_path = os.path.join(base_img_path, f"{valid_name}.jpg")
            try:
                response = await page.request.get(url)
                if response.ok:
                    content = await response.body()
                    with open(save_full_path, 'wb') as f:
                        f.write(content)
            except Exception as e:
                print(f"❌ 图片下载失败 {url}: {e}")
        
        async def traverse(index, current_names):
            if index == len(all_options):
                price_locator = page.locator('div.kYzukoxf div.ujEqGzEB')
                full_price = await price_locator.inner_text() if await price_locator.count() > 0 else "N/A"
                results.append(f"{' + '.join(current_names)} ({full_price.replace('¥', '').strip()})")
                
                # [修改] 读取价格后停留（模拟人类"看价格"）
                await human_delay(1, 3)
                
                sku_name = " + ".join(current_names)
                img_element = page.locator('div.O7pEFvHR img').first
                img_url = await img_element.get_attribute('src')
                if img_url:
                    clean_url = img_url.split('?')[0] if '?' in img_url else img_url
                    await rate_limiter.wait_if_needed('image_download')
                    await download_image(page, clean_url, sku_name)
                return
            
            count = await all_options[index].count()
            last_clicked_opt = None
            
            for i in range(count):
                opt = all_options[index].nth(i)
                class_attr = await opt.get_attribute("class") or ""
                
                if "uRVpnTQ1" in class_attr:
                    continue
                
                name = (await opt.get_attribute("aria-label") or await opt.inner_text()).strip()
                
                if "hr353bdX" not in class_attr:
                    # [关键修改] 使用 HumanMouse 点击 + 限流
                    await rate_limiter.wait_if_needed('sku_click')
                    await mouse.click_element(opt)
                    # [关键修改] 正态分布延迟替代固定0.4秒
                    await human_delay(1.0, 3.0)  # 1-3秒，而非0.4秒
                
                last_clicked_opt = opt
                await traverse(index + 1, current_names + [name])
            
            # 回溯清理
            if index > 0 and last_clicked_opt is not None:
                current_class_after = await last_clicked_opt.get_attribute("class") or ""
                if "hr353bdX" in current_class_after:
                    await mouse.click_element(last_clicked_opt)
                    await human_delay(0.8, 2.0)  # [修改] 替代固定0.3秒
                    print(f"🧹 清理低层状态: {current_names[-1] if current_names else 'Root'}")
        
        await traverse(0, [])
        return results

    async def run(self, url):
        target_keyword = "https://mobile.pinduoduo.com/goods_comments.html"
        async with async_playwright() as p:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]
            
            all_pages = context.pages
            page = None
            for p in all_pages:
                if target_keyword in p.url:
                    page = p
                    break
            
            if not page:
                print("❌ 未找到目标页面")
                return

            # [修改] 为当前页面注入反检测脚本（对后续导航生效）
            await page.add_init_script(STEALTH_JS)
            
            mouse = HumanMouse(page)
            
            # [修改] 用点击返回按钮替代 go_back
            back_btn = page.locator('button:has-text("返回"), .back-btn, [class*="back"]')
            if await back_btn.count() > 0:
                await mouse.click_element(back_btn.first)
            else:
                await page.go_back(wait_until="domcontentloaded")
            await human_delay(2, 4)
            
            goods_id = url.split("goods_id=")[-1].split("&")[0]
            
            # 提取标题
            title_selector = 'div.A6m4Y9EB.nFFS4Eh4 span.tLYIg_Ju'
            title_text = ""
            if await page.locator(title_selector).count() > 0:
                title_text = (await page.locator(title_selector).first.inner_text()).strip()
                print(f"🎯 标题提取成功: {title_text}")
            
            # [修改] 人性化滚动到参数区域
            await human_scroll(page, 'down', random.randint(800, 1500))
            await human_delay(1, 2.5)
            
            expand_btn = page.locator('div[role="button"]:has-text("查看全部")')
            if await expand_btn.count() > 0 and await expand_btn.is_visible():
                await mouse.click_element(expand_btn)  # [修改] 替代 expand_btn.click()
                await human_delay(0.5, 1.5)
            
            # 参数提取
            params_list = []
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
            await page.get_by_role("button", name="关闭对话框").click()

            # SKU 面板点击
            sku_trigger = page.locator('div.AANc1tSj div[role="button"]').last
            sku_price_data = []
            if await sku_trigger.count() > 0:
                await mouse.click_element(sku_trigger)  # [修改] 替代 sku_trigger.click()
                await human_delay(1, 2)
                
                spec_key_locators = page.locator('span.sku-specs-key')
                auto_specs = await spec_key_locators.all_inner_texts()
                spec_input = [s.strip() for s in auto_specs if s.strip()]
                print(f"检测到规格维度: {spec_input}")
                
                if spec_input:
                    sku_price_data = await self.collect_sku_combinations(page, spec_input, goods_id)
                
                # [修改] 关闭面板：移动到角落再点击
                await mouse.click(10, 10)
            
            sku_desc = " | ".join(sku_price_data)
            final_desc = (
                f"【商品标题】：{title_text}\n"
                f"【SKU价格详情】：{sku_desc}\n"
                f"【详细参数】：{' | '.join(params_list) if params_list else '暂无参数'}"
            )
            
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