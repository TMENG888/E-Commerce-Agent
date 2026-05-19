import json
import os
import sys
import time
from decimal import Decimal
import pyautogui
import pymysql
import pyperclip
import requests
from playwright.sync_api import sync_playwright
from base import Base
from generate_title import title_generation

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile"
"""

base = Base()
COOKIE_PATH = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_pro_cookies.json"


def get_goods_images(item_id):
    """
    从 goods_images 表获取指定 item_id 的图片列表，并按 sort_order 排序
    返回: [(sort_order, image_url), ...]
    """
    connection = pymysql.connect(**base.DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            # 查询 image_url 和 sort_order，按 sort_order 升序排列
            sql = "SELECT `sort_order`, `image_url` FROM `goods_images` WHERE `item_id` = %s ORDER BY `sort_order` ASC"
            cursor.execute(sql, (item_id,))
            results = cursor.fetchall()
            return results
    finally:
        connection.close()


def download_images_for_item(item_id, images_data):
    """
    下载图片到指定文件夹
    images_data: [(sort_order, image_url), ...]
    """

    # 构建目标文件夹路径: C:\Users\31193\Pictures\business_image\<item_id>
    target_folder = os.path.join(base.BASE_IMAGE_FOLDER, str(item_id))
    os.makedirs(target_folder, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    success_count = 0
    for sort_order, image_url in images_data:
        try:
            file_extension = ".jpg"
            file_name = f"{sort_order}{file_extension}"
            file_path = os.path.join(target_folder, file_name)

            response = requests.get(image_url, headers=headers, timeout=10)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ 已下载: {file_name}")
                success_count += 1
            else:
                print(f"❌ 下载失败 ({response.status_code}): {image_url}")

        except Exception as e:
            print(f"❌ 处理图片出错 (sort_id={sort_order}): {e}")

    print(f"🎉 完成！共成功下载 {success_count}/{len(images_data)} 张图片。")
    return target_folder


def get_goods_data(item_id):
    """从数据库获取指定 item_id 的商品信息"""
    connection = pymysql.connect(**base.DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            # SQL 查询语句
            sql = "SELECT * FROM `goods` WHERE `item_id` = %s"
            cursor.execute(sql, (item_id,))
            result = cursor.fetchone()
            return result
    finally:
        connection.close()


def upload_images_via_pyautogui(folder_path):
    """
    folder_path: 图片所在的文件夹绝对路径
    """
    # 1. 确保文件选择窗口已经弹出 (给一点缓冲时间)
    time.sleep(2)

    # 2. 定位到路径输入栏并输入地址
    # 技巧：Windows 选择窗口默认焦点通常不在路径栏，按 Alt+D 可以强制定位到路径栏
    pyautogui.hotkey('alt', 'd')
    time.sleep(0.5)

    # 使用 pyperclip 写入路径（解决中文路径无法直接输入的问题）
    pyperclip.copy(folder_path)
    pyautogui.hotkey('ctrl', 'v')
    pyautogui.press('enter')
    time.sleep(1)

    # 3. 全选图片
    # 先按一下 Tab 键将焦点移动到文件列表区域（通常需要按 2-3 次 Tab，取决于窗口布局）
    # 或者直接点击一下窗口中心位置
    pyautogui.press('tab', presses=4, interval=0.2)

    # 执行全选
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.5)

    # 4. 点击“打开”按钮 (Enter 键等同于点击“确定”)
    pyautogui.press('enter')
    print("✅ 文件上传指令已发送")


def run(target_item_id):
    images_data = get_goods_images(target_item_id)
    if not images_data:
        print(f"⚠️ 数据库中未找到 item_id 为 {target_item_id} 的图片数据")
        return
    else:
        # 执行下载
        downloaded_folder = download_images_for_item(target_item_id, images_data)
        goods = get_goods_data(target_item_id)
        if not goods:
            print(f"❌ 数据库中未找到 item_id 为 {target_item_id} 的数据")
            return

        print(f"✅ 已获取商品数据: {goods[5][:20]}...")

        with sync_playwright() as p:
            base.ensure_chrome_running()
            print("正在尝试接管已打开的 Chrome 实例 (port 9222)...")
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
            except Exception as e:
                print(f"无法连接到浏览器: {e}")
                return

            context = browser.contexts[0]
            page = context.new_page()

            with open(COOKIE_PATH, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            context.add_cookies(cookies)

            print("正在跳转至商品上架页面...")
            page.goto("https://www.goofish.pro/sale/product/add?from=%2Fon-sale")

            time.sleep(3)

            page.get_by_placeholder("请输入关键词").click()

            page.locator(".custom-cascader-node", has_text="其他").click()

            page.locator(".panel-list-item", has_text="其他闲置").nth(0).click()

            page.locator(".panel-list-item", has_text="其他闲置").nth(1).click()

            page.locator(".panel-list-item", has_text="其他闲置").nth(2).click()

            page.get_by_placeholder("请输入商品标题").fill(title_generation(target_item_id))

            input_description = page.get_by_placeholder("请输入商品描述")
            input_description.fill(goods[5])

            input_origin_price = page.get_by_placeholder("￥ 0.00").first
            input_origin_price.fill(str(goods[2] * Decimal('1.3')))

            input_price = page.get_by_placeholder("￥ 0.00").last
            input_price.fill(str(goods[2]))

            # page.locator('input[maxlength="9"]').fill("20")

            page.get_by_text("上传图片").click()

            upload_images_via_pyautogui(downloaded_folder)

            with open("page_source.html", "w", encoding="utf-8") as f:
                f.write(page.content())


if __name__ == "__main__":
    # 检查是否有命令行参数传入
    if len(sys.argv) > 1:
        target_item_id = sys.argv[1]
        print(f"接收到任务，准备上架商品 ID: {target_item_id}")
        run(target_item_id)
    else:
        print("未检测到参数，请双击网页 ID 触发")
