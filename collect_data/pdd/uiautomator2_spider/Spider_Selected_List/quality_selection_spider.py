import asyncio
import pymysql
from datetime import datetime

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

async def save_goods_to_db(data_list):
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        today = datetime.now().date()

        processed_data = [(*item, today) for item in data_list]

        sql = """
        REPLACE INTO pdd_rank_goods 
        (rank_num, goods_message, price, collect_date)
        VALUES (%s, %s, %s, %s)
        """
        cursor.executemany(sql, processed_data)
        conn.commit()  # 加上 commit
        print(f"✅ 保存成功：日期 {today}，共 {len(processed_data)} 条原始榜单商品")
    except Exception as e:
        print(f"❌ 保存失败：{e}")
    finally:
        if 'conn' in locals():
            conn.close()

# 核心修改：接收主程序传来的 page 对象
async def scrape_pdd_rank(page):
    await page.goto("https://mobile.pinduoduo.com/")
    await page.get_by_text("电脑").first.click()
    await page.get_by_text("品质优选").click()

    try:
        await page.wait_for_selector(".O2NVMcj3", timeout=10000)
    except Exception as e:
        print("未能在规定时间内找到商品列表，可能是页面没跳过去")
        return None

    # 执行滚动
    for _ in range(3):
        await page.mouse.wheel(0, 5000)
        await asyncio.sleep(1.5)

    goods_locators = page.locator(".O2NVMcj3")
    count = await goods_locators.count()

    extracted_data = []
    for i in range(count):
        element = goods_locators.nth(i)
        rank_num = await element.get_attribute("data-uniqid")
        title_text = await element.locator(".AjV7GyHv").inner_text()
        tags_text = await element.locator(".q9UHTf2L").inner_text()
        goods_message = f"{title_text.strip()} | {tags_text.strip()}".replace('\n', ' ')
        price = await element.locator(".vUuc_7v3").inner_text()

        extracted_data.append((int(rank_num), goods_message, price))

    return extracted_data

