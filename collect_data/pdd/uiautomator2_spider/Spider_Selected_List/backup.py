import asyncio
import random

import pymysql
from playwright.async_api import async_playwright
from base_backup import Base

CHROME_DEBUG_PORT = 9222
base = Base()

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

PROXIES = ["http://14.103.138.182:80","http://180.167.238.98:7302","http://60.12.215.23:7302","http://218.64.163.226:7302","http://115.239.234.43:7302","http://58.215.12.59:7302","http://112.13.209.132:8080","http://220.178.229.83:7302","http://103.25.26.135:80","http://1.71.170.146:7302","http://221.178.239.200:7302","http://223.80.109.182:7302","http://61.160.223.141:7302","http://218.6.152.149:7302","http://1.180.0.242:7302","http://183.61.28.254:8900","http://42.247.38.153:443","http://112.15.190.108:10086","http://61.134.48.51:7302","http://8.137.13.195:80","http://222.83.110.83:7302","http://101.132.172.223:8080","http://101.37.18.127:80","http://106.14.118.40:80","http://121.199.168.1:80","http://121.43.58.204:80","http://116.62.195.127:8080","http://101.37.19.73:80","http://58.241.88.13:800","http://123.56.253.145:10070"]


async def save_goods_to_db(data_list):
    """精简版保存数据到MySQL"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        sql = """
        INSERT INTO pdd_rank_goods 
        (rank_num, goods_message, price)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
        goods_message=VALUES(goods_message),
        price=VALUES(price)
        """

        cursor.executemany(sql, data_list)
        print(f"✅ 保存成功：共 {len(data_list)} 条商品")

    except Exception as e:
        print(f"❌ 保存失败：{e}")
    finally:
        if 'conn' in locals():
            conn.close()


async def run_pinduoduo():
    async with async_playwright() as p:
        # 连接已打开的浏览器
        current_proxy = random.choice(PROXIES)
        # 1. 连接到已经打开的浏览器
        base.ensure_chrome_running(proxy_url=current_proxy)
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        context = browser.contexts[0]
        page = await context.new_page()
        await page.add_init_script(path=r'/stealth.min.js')

        # 1. 进入页面
        await page.goto("https://mobile.pinduoduo.com/")

        # 2. 点击分类
        await page.get_by_text("电脑").first.click()
        # 点击后，页面会发生变化
        await page.get_by_text("品质优选").click()

        try:
            await page.wait_for_selector(".O2NVMcj3", timeout=10000)
        except Exception as e:
            print("未能在规定时间内找到商品列表，可能是页面没跳过去")
            return

        # 执行滚动
        for _ in range(3):
            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(1.5)  # 留给网络请求一点时间

        # 修正 2：改用 locator 循环，这样更健壮
        goods_locators = page.locator(".O2NVMcj3")
        count = await goods_locators.count()

        extracted_data = []
        for i in range(count):
            element = goods_locators.nth(i)

            # 获取排名
            rank_num = await element.get_attribute("data-uniqid")

            # 获取商品标题信息
            # 使用 locator 的 inner_text 会自动等待，比 query_selector 稳得多
            title_text = await element.locator(".AjV7GyHv").inner_text()
            tags_text = await element.locator(".q9UHTf2L").inner_text()

            # 清洗换行符
            goods_message = f"{title_text.strip()} | {tags_text.strip()}".replace('\n', ' ')

            # 获取价格
            price = await element.locator(".vUuc_7v3").inner_text()

            extracted_data.append((
                int(rank_num),
                goods_message,
                price
            ))

        # =====================================================

        if extracted_data:
            await save_goods_to_db(extracted_data)

        # 注意：如果你是 connect_over_cdp 开启的浏览器，通常不需要 browser.close()
        # await page.close()

# 运行
asyncio.run(run_pinduoduo())