import pymysql
import asyncio
from urllib.parse import urlparse, urlunparse, parse_qs

from base import Base

base = Base()

# 数据库连接配置
config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4'
}

# 1. 链接清洗函数：只保留 goods_id，去除推广参数
def clean_pdd_url(raw_url):
    u = urlparse(raw_url)
    query = parse_qs(u.query)
    # 只提取 goods_id 参数
    goods_id = query.get('goods_id', [''])[0]
    if goods_id:
        # 重新构造干净的链接
        return f"https://mobile.pinduoduo.com/goods.html?goods_id={goods_id}"
    return raw_url


# 2. 数据库更新函数：根据 original_index 回填 URL
def update_product_url(original_index, clean_url):
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        # 更新语句
        sql = "UPDATE selected_products SET detail_url = %s WHERE original_index = %s AND created_at = (SELECT max_time FROM (SELECT MAX(created_at) AS max_time FROM selected_products) AS temp_table)"
        cursor.execute(sql, (clean_url, original_index))
        # ⚠️ 关键点：一定要 commit，否则数据库不会有变化
        conn.commit()
        print(f"✅ 数据库更新成功：索引 {original_index} -> {clean_url}")
    except Exception as e:
        print(f"❌ 数据库更新失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


# 3. 核心业务逻辑：点击、抓取并保存
async def process_selected_products(page):
    # 先从数据库获取所有需要点击的索引
    try:
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT original_index FROM selected_products WHERE detail_url IS NULL AND created_at = (SELECT MAX(created_at) FROM selected_products)")
        indices = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        print(f"读取数据库索引失败: {e}")
        return

    for index in indices:
        # 构造选择器
        selector = f'div[data-uniqid="{index}"]'

        try:
            # 等待元素出现
            await page.wait_for_selector(selector, timeout=5000)

            # 点击商品进入详情页
            await page.click(selector)

            # 获取并清洗 URL
            current_url = page.url
            cleaned_url = clean_pdd_url(current_url)

            # 存入数据库
            update_product_url(index, cleaned_url)

            # 💡 关键操作：返回列表页，继续下一个点击
            await page.go_back()

            print(f"成功处理索引 {index}")

        except Exception as e:
            print(f"处理索引 {index} 时出错 (可能元素未在当前页): {e}")
            continue