import base64
import json
import subprocess
import time
from playwright.sync_api import sync_playwright
from Verification_code import recognize_captcha
import socket

from base import Base
engine_base = Base()

"""
运行自动化脚本前，请在终端打开以下浏览器实例，后续脚本方可接管浏览器
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\automation_profile"
"""

# --- 1. 账号字典配置 ---

ACCOUNTS = {

    "account1": {

        "phone": "13229689267",

        "password": "wt140140140",

        "cookie_name": "goofish_pro_13229689267.json"

    },

    "account2": {

        "phone": "13423605542",

        "password": "Wt140140140",

        "cookie_name": "goofish_pro_13423605542.json"

    }

}


def run(account_key=None):
    user_info = ACCOUNTS.get(account_key)
    if not engine_base.ensure_chrome_running():
        return

    with sync_playwright() as p:
        print("正在尝试接管已打开的 Chrome 实例 (port 9222)...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"无法连接到浏览器: {e}")
            return

        context = browser.contexts[0]
        page = context.new_page()

        print("正在跳转至闲管家登录页...")
        page.goto("https://www.goofish.pro/login")

        if "login" in page.url:
            # 判断是否需要点击“快速进入”或切换到账号密码登录
            if page.get_by_role("button", name="快速进入").is_visible():
                page.get_by_role("button", name="快速进入").click()
            else:
                page.locator('#tab-third').click()
                time.sleep(1)  # 等待面板切换

                # 查找验证码图片元素
                captcha_locator = page.locator('img[data-v-bad1fafc][src^="data:image"]')
                src_data = captcha_locator.get_attribute("src")

                if src_data and "base64," in src_data:
                    # 1. 解码并保存验证码图片
                    base64_str = src_data.split(",")[1]
                    img_bytes = base64.b64decode(base64_str)
                    file_name = "captcha_downloaded.png"
                    with open(file_name, "wb") as f:
                        f.write(img_bytes)
                    print(f"✨ 验证码图片已保存: {file_name}")

                    # --- 核心修改 2：调用 AI 识别 ---
                    print("🚀 正在调用 GLM-4V 接口进行识别...")
                    recognized_code = recognize_captcha(file_name)
                    print(f"🎉 识别结果: {recognized_code}")

                    # --- 核心修改 3：填入识别结果 ---
                    captcha_input = page.locator('input[placeholder="请输入验证码"][maxlength="4"]')
                    if "识别失败" not in recognized_code and len(recognized_code) <= 4:
                        captcha_input.fill(recognized_code)
                    else:
                        print("⚠️ 识别结果异常，请手动检查。")
                        # 如果识别失败，这里可以考虑手动输入或刷新验证码
                else:
                    print("❌ 未能获取到有效的验证码 Base64 数据")

                with open("page_source.html", "w", encoding="utf-8") as f:
                    f.write(page.content())

                # 定位第一个匹配“请输入手机号码”的输入框并填充
                page.locator('input[placeholder="请输入手机号码"]').first.fill(user_info['phone'])

                # 定位第一个匹配“请输入密码”的输入框并填充
                page.locator('input[placeholder="请输入密码"]').first.fill(user_info['password'])

                # 点击登录
                page.get_by_role("button", name="登录").click()
                page.wait_for_timeout(1000)

        # 检测登录成功并保存 Cookie
        try:
            print("🎉 登录成功！")
            time.sleep(1)

            cookies = context.cookies()
            with open("../cookie/alibaba_cookie/goofish_pro_cookies.json", "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=4)
            print("✅ Cookie 已保存")

            page.close()
        except Exception as e:
            print(f"❌ 登录确认超时或失败: {e}")


if __name__ == "__main__":
    run("account2")