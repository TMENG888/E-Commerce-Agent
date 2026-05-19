import json
import subprocess
import time
from playwright.sync_api import sync_playwright

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile
"""

def launch_chrome():
    # 1. 配置路径
    # 使用 r 前缀防止转义字符问题
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\selenium\automation_profile"
    remote_debugging_port = "9222"

    # 3. 构建命令行指令
    command = [
        chrome_path,
        f"--remote-debugging-port={remote_debugging_port}",
        f"--user-data-dir={user_data_dir}"
    ]

    # 4. 启动进程
    # 使用 Popen 不会阻塞 Python 代码的继续执行
    try:
        subprocess.Popen(command)
    except Exception as e:
        print(f"启动失败: {e}")

def run():
    launch_chrome()

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
        print("正在跳转至淘宝登录页...")
        page.goto("https://login.taobao.com/member/login.jhtml")

        if page.url == "https://login.taobao.com/havanaone/login/login.htm?bizName=taobao":
            if page.get_by_role("button", name="快速进入").is_visible():
                page.get_by_role("button", name="快速进入").click()
            else:
                # 2. 输入账号密码
                username = "13423605542"
                password = "Wt140140140"

                # 使用之前讨论过的 type 属性定位，更稳定
                page.wait_for_selector('input[type="text"]')
                page.fill('input[type="text"]', username)
                time.sleep(1)  # 稍微停顿

                page.wait_for_selector('input[type="password"]')
                page.fill('input[type="password"]', password)
                time.sleep(1)

                # 3. 点击登录
                page.click('button[type="submit"]')

                agree_button = page.locator('button.dialog-btn-ok')
                agree_button.click()

        # 5. 检测登录成功（通过检测“我的淘宝”或昵称元素）
        try:
            print("🎉 登录成功！")

            # 6. 获取并保存 Cookie
            cookies = context.cookies()
            with open("../cookie/alibaba_cookie/taobao_cookies.json", "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=4)
            print("✅ Cookie 已成功保存至 taobao_cookies.json")

            page.close()
        except Exception as e:
            print(f"❌ 流程中断或超时：{e}")


if __name__ == "__main__":
    run()