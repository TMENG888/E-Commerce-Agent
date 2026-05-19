import asyncio
import json
import os
import time
import pyautogui
import pymysql
import pyperclip
from playwright.async_api import async_playwright
from pymongo import MongoClient
from zai import ZhipuAiClient

API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"

# --- MongoDB 配置 ---
MONGO_CONFIG = {
    "host": "localhost",
    "port": 27017,
    "db": "Goofish",
    "collection": "Goods_Specification"
}


def title_generation(description=None):
    """依据商品描述生成电商标题"""

    prompt_text = f"""
       你是一位精通闲鱼、淘宝等电商平台的标题优化专家。
       任务：根据提供的【商品描述】和【商品图片】，生成一个极具吸引力的“爆款标题”。

       要求：
       1. 标题长度控制在 30-60 个汉字之间。
       2. 必须包含核心关键词、品牌（如果有）、成色、适用人群或场景。
       3. 语气要自然、真实，像个人卖家闲置转让，不要过于像广告。
       4. 适当加入一些热门流量词（如：包邮、急出、几乎全新、仅试用等），但要符合事实。
       5. 不要包含任何特殊符号（如【】、★等），只用中文和数字。

       【商品描述】：
       {description}

       请直接输出标题，不要包含“标题是：”等多余前缀。
       """
    try:
        client = ZhipuAiClient(api_key=API_KEY)
        response = client.chat.completions.create(
            model="GLM-4-Flash-250414",
            messages=[{"role": "user", "content": prompt_text}],
            stream=True,
            temperature=0.7,
            top_p=0.9
        )

        full_title = ""
        print("🚀 正在生成标题: ", end="")
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                full_title += content
                print(content, end="", flush=True)
        print("\n✅ 生成成功！")
        return full_title.strip()

    except Exception as e:
        print(f"❌ 生成标题失败: {str(e)}")
        return ""


class GoofishIntegrator:
    def __init__(self):
        self.cookie_path_upload = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_pro_cookies.json"
        self.chrome_debug_url = "http://localhost:9222"
        self.mongo_client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
        self.mongo_db = self.mongo_client[MONGO_CONFIG["db"]]
        self.mongo_col = self.mongo_db[MONGO_CONFIG["collection"]]

    def get_sku_data_from_mongo(self, goods_id):
        """从 MongoDB 获取该商品的所有规格维度和具体值"""
        cursor = self.mongo_col.find({"goods_id": goods_id})
        items = list(cursor)
        if not items:
            return None

        specs_map = {}  # 格式: {"颜色": {"象牙白", "泥土灰"}, "配置": {"3.5mm圆孔"}}
        exclude_keys = ["goods_id", "price", "original_sku", "_id"]

        for item in items:
            for key, value in item.items():
                if key not in exclude_keys:
                    if key not in specs_map:
                        specs_map[key] = set()
                    specs_map[key].add(value)

        return specs_map

    async def fill_sku_specifications(self, page, goods_id):
        """执行规格填写自动化"""
        specs_data = self.get_sku_data_from_mongo(goods_id)
        if not specs_data:
            print(f"⚠️ 商品 {goods_id} 在 MongoDB 中无规格数据，跳过规格填写。")
            return

        print(f"⚙️ 准备填写规格: {specs_data}")

        # 1. 点击“添加多规格深库存”
        await page.locator('div.sku-add-btn:has-text("添加多规格深库存")').click()
        await asyncio.sleep(1)

        # 2. 遍历规格维度 (例如: 颜色、配置)
        for idx, (spec_name, spec_values) in enumerate(specs_data.items()):

            # --- 核心修改点：处理第二个及以后的规格名 ---
            if idx > 0:
                # 如果是第二个规格，需要先点击“添加商品规格”按钮
                print(f"➕ 正在添加第 {idx + 1} 个规格维度: {spec_name}")
                add_spec_row_btn = page.locator('div.add-sku-one:has-text("添加商品规格")')
                await add_spec_row_btn.click()
                await asyncio.sleep(0.5)

            # 3. 输入规格类型名称 (如 "颜色")
            # 使用 nth(idx) 定位，因为每增加一行，就会多出一个 class 相同的 input
            spec_name_input = page.locator(f'.el-input__inner[placeholder*="商品规格{idx + 1}"]').nth(0)
            # 如果 placeholder 逻辑不严谨，也可以直接用全部 input 里的第 idx 个
            if await spec_name_input.count() == 0:
                spec_name_input = page.locator('.el-input__inner[placeholder*="商品规格"]').nth(idx)

            await spec_name_input.fill(spec_name)

            # 4. 点击该规格名行对应的“添加”按钮
            # 逻辑：寻找离当前 input 最近的那个“添加”按钮，或者使用 nth(0)，因为上方新出的按钮通常权重最高
            add_name_btn = page.locator('div.el-input:has(input[placeholder*="商品规格"]) + button:has-text("添加")')
            await add_name_btn.click()
            await asyncio.sleep(0.5)

            # 5. 遍历填写该维度下的具体规格值 (如 "象牙白", "泥土灰")
            for val in spec_values:
                # 定位具体规格值的输入框
                val_input = page.locator(f'.el-input__inner[placeholder*="请输入{spec_name}"]')
                await val_input.fill(val)

                # 点击规格值输入框旁边的“添加”按钮
                # 通常在一行中，最后出现的“添加”按钮是负责添加具体规格值的
                add_val_btn = page.locator('button.el-button--primary:has-text("添加")').last
                await add_val_btn.click()
                await asyncio.sleep(0.3)

        # 6. 点击最后的“确认”按钮完成全部规格库的建立
        confirm_btn = page.locator('button.el-button--primary:has-text("确认")')
        await confirm_btn.click()

        inventory_input = page.get_by_placeholder("库存（件）")
        await inventory_input.fill("10")

        set_button = page.locator('button.set-btn:has-text("批量设定")')
        await set_button.click()

        print("✅ 规格库填写并确认完成")

    async def upload_to_pro(self, goods_data, folder_path):
        print(f"🚀 开始异步上架到 Pro 端...")
        async with async_playwright() as p:
            # 连接现有浏览器
            browser = await p.chromium.connect_over_cdp(self.chrome_debug_url)
            context = browser.contexts[0]

            # 注入 Cookie
            if os.path.exists(self.cookie_path_upload):
                with open(self.cookie_path_upload, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto("https://www.goofish.pro/sale/product/add")

            # 1. 类目选择：增加超时等待，防止页面未加载完成
            try:
                await page.get_by_placeholder("请输入关键词").click()

                await page.locator(".custom-cascader-node", has_text="其他").click()

                await page.locator(".panel-list-item", has_text="其他闲置").nth(0).click()

                await page.locator(".panel-list-item", has_text="其他闲置").nth(1).click()

                await page.locator(".panel-list-item", has_text="其他闲置").nth(2).click()
            except Exception as e:
                print(f"⚠️ 类目选择可能异常: {e}")

            # 2. 文案处理
            description_content = goods_data['description'].strip()

            await page.get_by_placeholder("请输入商品标题").fill(title_generation(description_content))
            await page.get_by_placeholder("请输入商品描述").fill(description_content)

            await self.fill_sku_specifications(page, goods_data["goods_id"])

            # # 3. 价格填写
            # price = float(goods_data.get("price", 99))
            # await page.get_by_placeholder("￥ 0.00").first.fill(str(round(price * 1.3, 2)))
            # await page.get_by_placeholder("￥ 0.00").last.fill(str(price))

            # 4. 上传图片
            await page.get_by_text("上传图片").click()
            await asyncio.sleep(2)
            self._pyautogui_upload(folder_path)

            # 5. 等待图片上传完成（根据图片多少决定）
            print("⏳ 等待图片上传并解析...")
            await asyncio.sleep(8)

            # TODO: 如果需要自动点击发布，可以添加下行代码
            # await page.get_by_role("button", name="确认发布").click()
            print("✅ 填单完成，请核对后手动点击发布或取消注释自动发布。")

    def _pyautogui_upload(self, folder_path):
        time.sleep(2)
        pyautogui.hotkey('alt', 'd')
        time.sleep(0.5)
        pyperclip.copy(folder_path)
        pyautogui.hotkey('ctrl', 'v')
        pyautogui.press('enter')
        time.sleep(1)
        pyautogui.press('tab', presses=4, interval=0.2)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5)
        pyautogui.press('enter')


async def get_data_from_db(goods_id):
    """从数据库获取文案"""
    MYSQL_CONFIG = {
        'host': 'localhost', 'user': 'root', 'password': '123456',
        'database': 'pdd_db', 'charset': 'utf8mb4', 'autocommit': True
    }
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = "SELECT sales_desc FROM goods_descriptions WHERE goods_id = %s"
            cursor.execute(sql, (goods_id,))
            return cursor.fetchone()
    finally:
        conn.close()


async def main(target_goods_id):
    integrator = GoofishIntegrator()

    # 1. 从数据库读取指定的 sales_desc
    record = await get_data_from_db(target_goods_id)
    if not record or not record['sales_desc']:
        print(f"❌ 数据库中未找到 goods_id 为 {target_goods_id} 的有效文案")
        return

    # 2. 指定本地图片目录
    img_folder = os.path.join(r"C:\Users\31193\Pictures\上架图", str(target_goods_id))

    if not os.path.exists(img_folder):
        print(f"❌ 本地未找到图片目录: {img_folder}")
        return

    # 3. 组织上架数据
    goods_data = {
        "goods_id": target_goods_id,
        "description": record['sales_desc'],
        "price": 99,
    }

    # 4. 执行上架
    await integrator.upload_to_pro(goods_data, img_folder)

if __name__ == "__main__":
    target_id = "862194262588"
    asyncio.run(main(target_id))