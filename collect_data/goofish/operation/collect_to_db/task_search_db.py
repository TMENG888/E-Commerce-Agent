import json
import re
import pymysql
import random
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from base import Base

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile"
"""

COOKIE_PATH = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_cookies.json"
base = Base()


class GoofishListScraper:
    def __init__(self):
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.search_keyword = "有线键盘"  # 定义搜索品类词
        self.init_db()

    def init_db(self):
        """初始化数据库：创建任务表，添加 page 和 category 字段"""
        conn = pymysql.connect(**base.DB_CONFIG)
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS goofish_tasks (
                    id INT AUTO_INCREMENT PRIMARY KEY,          -- 自增逻辑 ID
                    item_id VARCHAR(50) NOT NULL UNIQUE,       -- 商品 ID (唯一)
                    link TEXT,                                 -- 商品链接
                    status INT DEFAULT 0,                      -- 状态：0未采集 1已采集 2失败
                    page INT,                                  -- 对应页码 (新增)
                    category VARCHAR(100),                     -- 对应品类 (新增)
                    create_date DATE                           -- 创建日期
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            conn.commit()
            print("✅ 数据库初始化完成 (包含 Page & Category 字段)")
        finally:
            conn.close()

    def parse_and_save(self, html_content, page_num):
        """解析 HTML 并存入数据库"""
        soup = BeautifulSoup(html_content, 'html.parser')
        items = soup.find_all('a', class_=lambda x: x and x.startswith('feeds-item-wrap'))

        conn = pymysql.connect(**base.DB_CONFIG)
        try:
            with conn.cursor() as cursor:
                for item in items:
                    try:
                        link = item.get('href', '')
                        if link.startswith('//'): link = 'https:' + link

                        # 提取核心 ID
                        item_id_match = re.search(r'id=(\d+)', link)
                        item_id = item_id_match.group(1) if item_id_match else None
                        if not item_id: continue

                        # 插入数据库：如果 ID 重复则更新
                        sql = """
                        INSERT INTO goofish_tasks (item_id, link, status, page, category, create_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                            page=VALUES(page),
                            category=VALUES(category)
                        """
                        cursor.execute(sql, (
                            item_id, link, 0, page_num, self.search_keyword, self.today
                        ))
                    except Exception as e:
                        print(f"解析详情失败: {e}")
            conn.commit()
        finally:
            conn.close()

    def run(self):
        start_page = 1
        conn = pymysql.connect(**base.DB_CONFIG)
        try:
            with conn.cursor() as cursor:
                # 查询当前品类下已抓取的最大页码
                cursor.execute("SELECT MAX(page) FROM goofish_tasks WHERE category = %s and create_date = current_date", (self.search_keyword,))
                result = cursor.fetchone()
                if result and result[0]:
                    start_page = result[0] + 1  # 从最后一页的下一页开始
        finally:
            conn.close()

        if start_page > 50:
            print(f"🏁 品类 [{self.search_keyword}] 已完成 50 页采集，无需继续。")
            return

        with sync_playwright() as p:
            print("正在连接浏览器...")
            # 这里的端口 9222 需确保你已经先用 debug 模式打开了 Chrome
            base.ensure_chrome_running()
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]

            # 注入 Cookie
            with open(COOKIE_PATH, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            context.add_cookies(cookies)

            page = context.pages[0]
            # 使用变量拼接 URL
            url = f"https://www.goofish.com/search?q={self.search_keyword}"
            page.goto(url)
            page.wait_for_timeout(2000)

            if start_page > 1:
                print(f"跳转至断点页码: {start_page}")
                try:
                    # 定位输入框并输入页码
                    input_selector = "input.search-pagination-to-page-input--NDqqDgSl"
                    page.wait_for_selector(input_selector)
                    page.fill(input_selector, str(start_page))

                    # 点击确定按钮 (使用你提供的 class 或 xpath)
                    confirm_btn = page.locator("button.search-pagination-to-page-confirm-button--b51GmTKS")
                    confirm_btn.click()

                    # 等待跳转后的页面加载
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"❌ 跳转分页失败: {e}")

                # --- 修改循环范围 ---
            for i in range(start_page - 1, 50):  # 从 start_page 开始，总数 50
                current_page_idx = i + 1

                # 等待列表加载
                try:
                    # 使用 wait_for_selector 确保页面渲染
                    page.wait_for_selector("a[class^='feeds-item-wrap']", timeout=10000)
                except Exception:
                    print("⚠️ 等待超时，尝试刷新页面...")
                    page.reload()
                    page.wait_for_timeout(3000)

                # 获取内容并解析入库
                content = page.content()
                self.parse_and_save(content, current_page_idx)

                # 点击下一页
                try:
                    next_btn = page.locator("//button[./div[contains(@class, 'search-pagination-arrow-right')]]")
                    if next_btn.is_visible() and next_btn.is_enabled():
                        next_btn.click()
                        # 随机延迟防封
                        page.wait_for_timeout(random.randint(500, 1000))
                    else:
                        print("🔚 到达最后一页或下一页按钮不可见")
                        break
                except Exception as e:
                    print(f"❌ 翻页操作失败: {e}")
                    break

            print(f"✅ 品类 [{self.search_keyword}] 采集任务结束")


if __name__ == "__main__":
    scraper = GoofishListScraper()
    scraper.run()