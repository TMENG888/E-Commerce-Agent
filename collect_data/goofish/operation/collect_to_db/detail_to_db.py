import json
import asyncio
import os
import re
import sys
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
slider_path = os.path.join(project_root, "Anti-crawler_bypassing")
sys.path.append(slider_path)
from Slider import solve_captcha, get_slider_coordinate_opencv

import pymysql
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from base import Base

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile"
"""

# --- 配置 ---
COOKIE_PATH = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_cookies.json"
MAX_CONCURRENT = 8

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'goofish_db',
    'charset': 'utf8mb4',
    'autocommit': True  # 自动提交事务
}

# 全局控制量
semaphore = asyncio.Semaphore(MAX_CONCURRENT)
pause_event = asyncio.Event()
pause_event.set()

active_tasks_count = 0        # 记录当前存活的任务数
tasks_lock = asyncio.Lock()   # 保护计数器的锁
solving_lock = asyncio.Lock()

base = Base()


# --- 解析与数据库操作类 ---
class GoofishDataProcessor:
    @staticmethod
    def extract_clean_text(html_content):
        # 1. 预处理：将常见的块级标签和换行标签替换为占位符
        # 有些 span 之间没有 br 但在页面上是换行的，这里统一处理
        soup = BeautifulSoup(html_content, 'html.parser')

        # 2. 获取文本。使用 separator="\n" 可以强制将每个标签的边界视为换行
        # strip=False 确保我们不会误删行内的空格
        raw_text = soup.get_text(separator="\n", strip=False)

        # 3. 按行处理，沿袭原本的空格逻辑
        lines = raw_text.splitlines()
        processed_lines = []

        for line in lines:
            # 保持原始空格，但去掉前后极其细微的不可见字符（如 \u200b）
            clean_line = line.replace('\u200b', '').replace('\xa0', ' ')
            # 如果这一行全是空白，我们只保留一个空行
            if not clean_line.strip():
                processed_lines.append("")
            else:
                processed_lines.append(clean_line)

        # 4. 重新组合
        content = "\n".join(processed_lines)

        return re.sub(r'展开$', '', content.strip())

    def parse_all(html_content, item_id):
        # 1. 解析商品基础信息
        price_match = re.search(r'class="price--[^"]*"[^>]*>([\d.]+)', html_content)
        price = float(price_match.group(1)) if price_match else 0.0

        want_match = re.search(r'(\d+)人想要.*?(?=[\s\d\.万]*浏览)', html_content)
        want_count = int(want_match.group(1)) if want_match else 0

        view_match = re.search(r'([\d.]+万?)浏览', html_content)
        raw_v = view_match.group(1) if view_match else "0"

        image_container_match = re.search(r'<div class="item-main-window-list--[^"]+".*?>(.*?)<div class="item-main-window-carousel--', html_content, re.S).group(1)
        image_match = re.findall(r'src="//([^"]+?\.jpg)', image_container_match)
        image_urls = list(dict.fromkeys([f"https://{url}" for url in image_match]))

        desc_match = re.search(r'class="desc--[^>]*">([\s\S]*?)</div>', html_content)
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(html_content)

        if "买家可退货且运费由卖家承担" in desc_match.group(1):
            desc_match = re.search(r'class="notLoginContainer--hQCDYhxp"[\s\S]*?text-align: justify;">([\s\S]*?)</div>\s*</div>', html_content)
            description = GoofishDataProcessor.extract_clean_text(desc_match.group(1))
        else:
            description = GoofishDataProcessor.extract_clean_text(desc_match.group(1))

        user_id_match = re.search(r'userId=(\d+)', html_content)
        user_id = user_id_match.group(1) if user_id_match else None

        goods_data = {
            "item_id": item_id,
            "price": price,
            "want_count": want_count,
            "view_count": int(float(raw_v.replace('万', '')) * 10000) if '万' in raw_v else int(raw_v),
            "description": description,
            "business_id": user_id,
            "item_url": f'https://www.goofish.com/item?id={item_id}'
        }

        # 2. 解析商家信息
        nick_m = re.search(r'class="item-user-info-nick--[^"]*">([^<]+)</div>', html_content)
        all_labels = re.findall(r'class="item-user-info-label--[^"]*">([^<]+)</div>', html_content)

        business_data = {
            "business_id": user_id,
            "nickname": nick_m.group(1) if nick_m else "",
            "location": all_labels[0] if len(all_labels) > 0 else "",
            "online_time": all_labels[1] if len(all_labels) > 1 else "",
            "join_year": all_labels[2] if len(all_labels) > 2 else "",
            "sales_count": all_labels[3] if len(all_labels) > 3 else "",
            "rating": all_labels[4] if len(all_labels) > 4 else "",
            "business_url": f"https://www.goofish.com/personal?userId={user_id}" if user_id else ""
        }
        return goods_data, business_data, image_urls


    @staticmethod
    def update_task_and_data(db_conn, item_id, goods, biz, image_urls, status_code):
        """
        status_code: 1-成功, 2-数据不全/失败, 3-宝贝被删除
        """
        today = datetime.now().strftime('%Y-%m-%d')
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            with db_conn.cursor() as cursor:
                if status_code == 1:
                    # 获取品类
                    cursor.execute("SELECT category FROM goofish_tasks WHERE item_id = %s", (item_id,))
                    result = cursor.fetchone()
                    category_val = result[0] if result else None

                    # --- A. 写入/更新 商家表 ---
                    # 使用 ON DUPLICATE KEY UPDATE。注意 created_at 不在更新列表中，只在首次插入时生效
                    biz_sql = """
                        INSERT INTO businesses (
                            business_id, nickname, location, online_time, join_year, 
                            sales_count, rating, business_url, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                            nickname=VALUES(nickname), 
                            location=VALUES(location),
                            online_time=VALUES(online_time),
                            sales_count=VALUES(sales_count),
                            rating=VALUES(rating),
                            updated_at=VALUES(updated_at)
                        """

                    cursor.execute(biz_sql, [
                        biz['business_id'], biz['nickname'], biz['location'],
                        biz['online_time'], biz['join_year'], biz['sales_count'],
                        biz['rating'], biz['business_url'], today, now_ts
                    ])

                    # --- B. 写入商品历史表 ---
                    # 使用 INSERT IGNORE 或 REPLACE，配合联合唯一索引 (item_id, collect_date)
                    goods_sql = """
                        INSERT IGNORE INTO goods (
                            item_id, price, want_count, view_count, description, 
                            business_id, item_url, collect_date, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """

                    cursor.execute(goods_sql, [
                        goods['item_id'], goods['price'], goods['want_count'],
                        goods['view_count'], goods['description'], goods['business_id'],
                        goods['item_url'], today, category_val
                    ])

                    # --- C. 写入商品图片表 ---
                    image_batch = [(item_id, url, i + 1) for i, url in enumerate(image_urls)]
                    cursor.execute("DELETE FROM goods_images WHERE item_id = %s AND DATE(collect_date) = %s",
                                   (item_id, today))
                    img_sql = "INSERT INTO goods_images (item_id, image_url, sort_order) VALUES (%s, %s, %s)"
                    cursor.executemany(img_sql, image_batch)

                    # --- C. 更新任务状态 ---
                    cursor.execute("UPDATE goofish_tasks SET status = 1 WHERE item_id = %s", (item_id,))
                    print(f"✨ ID: {item_id} 数据已更新 (日期: {today})")

                elif status_code == 3:
                    # 状态 3：明确识别为宝贝被删除
                    cursor.execute("UPDATE goofish_tasks SET status = 3 WHERE item_id = %s",
                                   (item_id,))
                    print(f"🗑️ ID: {item_id} 确认已删除")

                else:
                    cursor.execute("UPDATE goofish_tasks SET status = 2 WHERE item_id = %s", (item_id,))
                    print(f"⚠️ ID: {item_id} 数据不全，已标记失败")
            return True
        except Exception as e:
            print(f"❌ 写入 ID {item_id} 数据库失败: {e}")
            return False


# --- 并发抓取核心 ---
async def fetch_and_process(context, item_id, url, db_conn):
    global active_tasks_count

    async with semaphore:
        async with tasks_lock:
            active_tasks_count += 1

        await pause_event.wait()

        try:
            await pause_event.wait()
            page = await context.new_page()
            print(f"🚀 正在处理 ID: {item_id}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)

            # --- 核心修改：检查宝贝是否被删除 ---
            # 使用你提供的文字特征，这是最准确的
            is_deleted = await page.get_by_text("糟糕！宝贝被删掉了").is_visible() | await page.get_by_text("跨境商品").first.is_visible()

            if is_deleted:
                GoofishDataProcessor.update_task_and_data(db_conn, item_id, None, None, None, status_code=3)
                return  # 终止后续解析流程

            # 滑块检测
            baxia_frame = page.frame_locator("xpath=/html/body/div[5]/iframe")
            slider = baxia_frame.locator("xpath=//*[@id='nc_1_n1z']")

            while await slider.is_visible():
                if pause_event.is_set():
                    pause_event.clear()
                    print(f"🛑 触发滑块，拦截后续任务...")

                async with solving_lock:
                    if not await slider.is_visible():
                        pause_event.set()
                        break
                    else:
                        max_retries = 3
                        retry_count = 0
                        is_solved = False
                        while retry_count < max_retries:
                            retry_count += 1
                            print(f"📸 [第 {retry_count} 次尝试]开始自动破解...")
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, solve_captcha)
                            await asyncio.sleep(2)

                            # 破解完成后，恢复全局运行
                            if not await slider.is_visible():
                                print("✅ 滑块已破解，恢复全体任务")
                                is_solved = True
                                break

                            else:
                                print(f"⚠️ 第 {retry_count} 次失败，正在刷新滑块重试...")
                                await page.reload()
                                await asyncio.sleep(2)

                        if is_solved:
                            print("🚀 全体恢复：所有线程继续运行")
                            pause_event.set()
                            await page.reload()
                        else:
                            print("❌ 多次重试均失败，进入人工介入模式")
                            await loop.run_in_executor(None, input, "💔 自动破解全数失败，请手动滑动后按 [Enter]...")
                            pause_event.set()

            # --- 解析数据 ---
            html_content = await page.content()
            goods, biz, image_urls = GoofishDataProcessor.parse_all(html_content, item_id)

            # 验证数据完整性
            is_valid = all([
                goods['view_count'] > 0,
                goods['business_id'] is not None,
                len(goods['description']) > 0,
                image_urls is not None
            ])

            status = 1 if is_valid else 2
            GoofishDataProcessor.update_task_and_data(db_conn, item_id, goods, biz, image_urls, status)

        except Exception as e:
            print(f"❌ 访问 ID {item_id} 出错: {e}")
            # 更新为失败状态
            with db_conn.cursor() as c:
                c.execute("UPDATE goofish_tasks SET status = 2 WHERE item_id = %s", (item_id,))
        finally:
            await page.close()


def init_detail_tables():
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 1. 商家表：增加创建和更新时间
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                business_id VARCHAR(50) UNIQUE,
                nickname VARCHAR(100),
                location VARCHAR(50),
                online_time VARCHAR(50),
                join_year VARCHAR(50),
                sales_count VARCHAR(50),
                rating VARCHAR(20),
                business_url TEXT,
                created_at DATE,              -- 首次入库日期
                updated_at DATETIME           -- 资料更新时间
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 2. 商品表：增加采集日期，并设置联合唯一索引以支持历史记录
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS goods (
                id INT AUTO_INCREMENT PRIMARY KEY,
                item_id VARCHAR(50),
                price DECIMAL(10, 2),
                want_count INT,
                view_count INT,
                description TEXT,
                business_id VARCHAR(50),
                item_url TEXT,
                collect_date DATE,            -- 采集日期 (YYYY-MM-DD)
                category VARCHAR(100),
                UNIQUE KEY `idx_item_date` (item_id, collect_date) -- 核心：同ID同日期唯一
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        conn.commit()
        print("✅ 数据库表结构初始化/更新完成")
    finally:
        conn.close()


async def main():
    # --- 执行初始化 ---
    init_detail_tables()

    # 1. 从数据库获取任务
    db_conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with db_conn.cursor() as cursor:
            # 获取待采集和失败任务
            cursor.execute("SELECT item_id, link FROM goofish_tasks WHERE status IN (0, 2)")
            # 获取待更新任务
            # cursor.execute("SELECT item_id, link FROM goofish_tasks WHERE status = 1 AND category = '盲盒'")
            tasks = cursor.fetchall()  # 结果为 ((id, link), (id, link)...)
    except Exception as e:
        print(f"读取任务表失败: {e}")
        return

    if not tasks:
        print("🙌 暂无待处理任务 (status=0)")
        return

    print(f"📂 发现 {len(tasks)} 条待抓取任务")

    if not base.ensure_chrome_running():
        return

    # 2. 启动浏览器
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # 注入 Cookie
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)

        # 3. 分配并发任务
        task_list = []
        for item_id, link in tasks:
            task_list.append(fetch_and_process(context, item_id, link, db_conn))

        await asyncio.gather(*task_list)

    db_conn.close()
    print("\n🏁 所有任务执行完毕。")


if __name__ == "__main__":
    asyncio.run(main())