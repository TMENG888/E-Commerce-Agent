"""
闲鱼商品下架工具
功能：根据商品ID列表，在商品管理页面批量下架商品
"""

import json
import time
import socket
import subprocess
from playwright.sync_api import sync_playwright

GOODS_MANAGE_URL = "https://seller.goofish.com/?site=COMMONPRO#/seller-item/goods-manage"
COOKIE_PATH = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_cookies.json"


def is_port_open(port):
    """检查本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def ensure_chrome_running():
    """确保 Chrome 浏览器以调试模式运行"""
    port = 9222
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\selenium\automation_profile"

    if is_port_open(port):
        print(f"✅ 端口 {port} 已开启，准备接管现有浏览器实例...")
    else:
        print(f"🌐 端口 {port} 未开启，正在启动新浏览器实例...")
        command = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            subprocess.Popen(command)
            time.sleep(3)
            print("✅ 浏览器启动成功")
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False
    return True


def unlist_single_goods(page, goods_id):
    """下架单个商品，返回是否下架成功"""
    try:
        unlist_btn = page.locator('a.operaBtn--Ur1hcVNu').filter(has_text='下架')
        if unlist_btn.count() > 0:
            unlist_btn.first.click()
            time.sleep(1)

            page.evaluate("""() => {
                document.querySelectorAll('.ant-btn-primary')[1].click();
            }""")
            print(f"   ✅ 商品 {goods_id} 下架成功")
            time.sleep(2)
            return True
        else:
            print(f"   ⚠️ 商品 {goods_id} 未找到下架按钮")
            return False
    except Exception as e:
        print(f"   ❌ 商品 {goods_id} 下架失败: {e}")
        return False


def unlist_goods_by_ids(goods_ids):
    """
    根据商品ID列表批量下架商品
    goods_ids: 商品ID列表，如 ['123456', '789012', '345678']
    """
    if not goods_ids:
        print("⚠️ 商品ID列表为空")
        return

    goods_ids_str = ','.join(str(gid) for gid in goods_ids)
    print(f"📋 待下架商品ID列表: {goods_ids_str}")

    print("\n🔗 检查浏览器状态...")
    if not ensure_chrome_running():
        return

    with sync_playwright() as p:
        print("\n🔗 连接浏览器...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 无法连接到浏览器: {e}")
            return

        context = browser.contexts[0]

        print("\n🔐 加载cookies...")
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)

        print("\n🌐 访问商品管理页面...")
        page = context.new_page()
        page.goto(GOODS_MANAGE_URL, wait_until="networkidle", timeout=60000)
        time.sleep(5)

        print("\n🔍 输入商品ID进行筛选...")
        try:
            input_box = page.locator('input.ant-input[placeholder="多个ID以逗号分隔"]')
            input_box.fill(goods_ids_str)
            print(f"   ✅ 已输入商品ID: {goods_ids_str}")
            time.sleep(1)

            filter_btn = page.locator('button.ant-btn-primary').filter(has_text='确认筛选')
            filter_btn.click()
            print("   ✅ 已点击确认筛选按钮")
            time.sleep(3)
        except Exception as e:
            print(f"   ❌ 输入商品ID或点击筛选失败: {e}")
            page.close()
            return

        total_unlisted = 0
        total_failed = 0
        goods_ids_set = set(str(gid) for gid in goods_ids)
        processed_ids = set()

        while True:
            unlist_buttons = page.locator('a.operaBtn--Ur1hcVNu').filter(has_text='下架')
            button_count = unlist_buttons.count()
            print(f"\n📦 当前页面发现 {button_count} 个可下架商品")

            if button_count == 0:
                break

            for i in range(button_count):
                try:
                    unlist_btn = unlist_buttons.nth(i)
                    unlist_btn.click()
                    time.sleep(1)

                    page.evaluate("""() => {
                        document.querySelectorAll('.ant-btn-primary')[1].click();
                    }""")
                    print(f"   ✅ 下架成功")
                    time.sleep(2)

                    total_unlisted += 1
                except Exception as e:
                    print(f"   ❌ 下架失败: {e}")

            if total_unlisted + total_failed >= len(goods_ids_set):
                break

            next_page_btn = page.locator('li.ant-pagination-next:not(.ant-pagination-disabled)')
            if next_page_btn.count() > 0:
                print("\n📄 翻页到下一页...")
                next_page_btn.click()
                time.sleep(3)
            else:
                print("⚠️ 已到达最后一页，无更多商品")
                break

        print(f"\n{'='*60}")
        print(f"📊 下架统计:")
        print(f"   ✅ 成功下架: {total_unlisted} 个商品")
        print(f"   ❌ 下架失败: {total_failed} 个商品")
        print(f"{'='*60}")

        page.close()


if __name__ == "__main__":
    print("=" * 60)
    print("🗑️  闲鱼商品批量下架工具")
    print("=" * 60)
    print("\n请输入要下架的商品ID，多个ID用逗号分隔：")
    print("示例: 123456,789012,345678")
    print("-" * 60)

    user_input = input("\n请输入商品ID列表: ").strip()

    if not user_input:
        print("⚠️ 输入为空，程序退出")
        exit()

    goods_ids = [gid.strip() for gid in user_input.split(',') if gid.strip()]

    if not goods_ids:
        print("⚠️ 未识别到有效商品ID，程序退出")
        exit()

    print(f"\n📋 识别到 {len(goods_ids)} 个商品ID: {goods_ids}")

    confirm = input("\n确认开始下架操作? (y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消操作")
        exit()

    unlist_goods_by_ids(goods_ids)

    print("\n🎉 程序执行完成")