import json
import socket
import subprocess
import time
from playwright.sync_api import sync_playwright

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile"
"""


def is_port_open(port):
    """检查本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # 设置超时时间，避免长时间阻塞
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def ensure_chrome_running():
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
            "--no-first-run",  # 跳过首次运行引导
            "--no-default-browser-check" # 跳过默认浏览器检查
        ]
        try:
            # 使用 Popen 后，给浏览器一点点启动时间
            subprocess.Popen(command)
            time.sleep(2)
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False
    return True

def run():
    if not ensure_chrome_running():
        return

    with sync_playwright() as p:
        # 注意：这里不再使用 launch，而是使用 connect_over_cdp
        # 端口 9222 必须与你命令行启动的端口一致
        print("正在尝试接管已打开的 Chrome 实例 (port 9222)...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"无法连接到浏览器，请确保你已经运行了启动命令且关闭了所有普通 Chrome 窗口。错误: {e}")
            return

        context = browser.contexts[0]

        page = context.new_page()

        # 1. 访问淘宝登录页
        print("正在跳转至闲鱼登录页...")
        page.goto("https://www.goofish.com/")
        time.sleep(1)

        login_iframe = page.frame_locator("#alibaba-login-box")

        if page.locator('a[href*="/personal"]').count() == 0:
            # 2. 输入账号密码
            username = "13423605542"
            password = "Wt140140140"

            # 使用之前讨论过的 type 属性定位，更稳定
            login_iframe.locator("#fm-login-id").fill(username)
            time.sleep(1)
            login_iframe.locator("#fm-login-password").fill(password)
            time.sleep(1)
            # 3. 点击登录
            login_iframe.get_by_role("button", name="登录").click()

            agree_button = login_iframe.locator('button.dialog-btn-ok')
            agree_button.click()

        # 5. 检测登录成功（通过检测“我的淘宝”或昵称元素）
        try:
            print("🎉 登录成功！")
            time.sleep(1)

            # 6. 获取并保存 Cookie
            cookies = context.cookies()
            with open("../cookie/alibaba_cookie/goofish_cookies.json", "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=4)
            print("✅ Cookie 已成功保存至 goofish_cookies.json")

            page.close()

        except Exception as e:
            print(f"❌ 流程中断或超时：{e}")


if __name__ == "__main__":
    run()