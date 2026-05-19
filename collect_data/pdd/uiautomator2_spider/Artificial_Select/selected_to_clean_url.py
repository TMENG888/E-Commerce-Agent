import asyncio
import time
import pymysql
import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
from base import Base

# 假设这是你的数据库配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}
base = Base()


def clean_pdd_url(raw_url):
    """提取 goods_id 并重组标准 URL"""
    if not raw_url: return None
    u = urlparse(raw_url)
    query = parse_qs(u.query)
    # 兼容拼多多各种跳转后的 goods_id 提取
    goods_id = query.get('goods_id', [None])[0]
    if goods_id:
        return f"https://mobile.pinduoduo.com/goods.html?goods_id={goods_id}"
    return raw_url


async def get_real_urls(input_urls):
    """
    启动浏览器，逐个访问原始 URL 并获取跳转后的最终 URL
    """
    raw_list = input_urls.replace(' ', ',').replace('\t', ',').split(',')
    results = []
    REQUIRED_PREFIX = "https://mobile.pinduoduo.com/goods.html?goods_id="

    CHROME_DEBUG_PORT = 9222
    async with async_playwright() as p:
        try:
            base.ensure_chrome_running()
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            for url in raw_list:
                url = url.strip()
                if not url: continue

                print(f"🌐 正在访问: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    final_url = page.url
                    cleaned = clean_pdd_url(final_url)

                    # --- 🚀 新增：核心检测逻辑 ---
                    if not cleaned or REQUIRED_PREFIX not in cleaned:
                        print(f"❌ 检测到异常链接: {final_url}")
                        print("🚨 清洗后的链接不符合标准格式，程序将终止，请人工排查！")
                        # 抛出异常以彻底中断整个异步流程
                        raise ValueError(f"访问异常：链接 '{final_url}' 无法解析为标准商品页")
                    # ---------------------------

                    results.append(cleaned)
                    print(f"✨ 成功获取清洗后URL: {cleaned}")
                except ValueError as ve:
                    # 重新抛出自定义的异常，让外层捕获
                    raise ve
                except Exception as e:
                    print(f"⚠️ 访问跳过 {url}: {e}")

            await browser.close()
        except Exception as e:
            # 如果是自定义的异常，直接向上抛出
            if isinstance(e, ValueError):
                raise e
            print(f"❌ 浏览器连接失败: {e}")

    return results


def db_insert_final(urls):
    """执行数据库入库"""
    if not urls: return
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        sql = "INSERT INTO selected_products (detail_url, original_index) VALUES (%s, %s)"

        insert_data = [(url, int(time.time()) + i) for i, url in enumerate(urls)]
        cursor.executemany(sql, insert_data)
        conn.commit()
        print(f"✅ 最终入库成功：已保存 {len(insert_data)} 条商品")
    except Exception as e:
        print(f"❌ 数据库写入错误: {e}")
    finally:
        if 'conn' in locals(): conn.close()


async def main():
    # 1. 接收输入
    user_input = input("请输入拼多多商品URL（逗号分隔）: ")
    if not user_input.strip(): return

    # 2. 异步访问获取真实连接
    print("🚀 开始通过浏览器获取真实 URL...")
    try:
        final_urls = await get_real_urls(user_input)
    except ValueError as e:
        print(f"\n🛑 程序已终止运行：{e}")
        return

    # 3. 结果去重
    unique_urls = list(set(final_urls))

    # 4. 同步入库
    db_insert_final(unique_urls)


if __name__ == "__main__":
    asyncio.run(main())
