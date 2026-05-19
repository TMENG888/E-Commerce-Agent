import asyncio
import random
import subprocess
import socket

from playwright.async_api import async_playwright
import time

from base import Base

base = Base()

PROXY_ADDR = "static-qiye.hailiangip.com"
PROXY_PORT = "41812"
PROXY_USER = "O26042415331360363035_1"
PROXY_PASS = "h8p0SgRL"


def is_port_open(port):
    """检查本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # 设置超时时间，避免长时间阻塞
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def kill_chrome():
    """强制关闭所有 Chrome 进程，确保新代理能生效"""
    try:
        subprocess.run('taskkill /F /IM chrome.exe', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except:
        pass


async def test_single_proxy():
    kill_chrome()

    # 使用修改后的启动逻辑
    if not ensure_chrome_running():
        return False

    # 关键修复：使用 async with
    async with async_playwright() as p:
        print(f"正在尝试接管 Chrome 实例验证代理...")
        try:
            # 连接浏览器
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]

            async def handle_route(route):
                # 手动构造 Basic Auth 响应
                import base64
                auth_str = f"{PROXY_USER}:{PROXY_PASS}"
                auth_b64 = base64.b64encode(auth_str.encode()).decode()
                headers = {
                    **route.request.headers,
                    "Proxy-Authorization": f"Basic {auth_b64}"
                }
                await route.continue_(headers=headers)

            # 在 page 创建后增加拦截
            page = await context.new_page()
            await page.route("**/*", handle_route)
            # 关键修复：异步环境下创建页面需要 await
            page = await context.new_page()

            # 验证实际出口 IP
            await page.goto("https://2026.ip138.com/", timeout=10000)
            ip_element = page.locator('a[href*="ip138.com/iplookup.php"]')

            # 打印文本（IP地址）
            ip_text = await ip_element.inner_text()
            print("IP 地址：", ip_text)

            await browser.close()
            return True
        except Exception as e:
            print(f"❌ 验证出错: | 错误: {e}")
            return False


# 对应的 ensure_chrome_running 建议放在此文件中或修改 base.py
def ensure_chrome_running():
    port = 9222
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\selenium\automation_profile"

    # 注意：这里不再检查端口，因为 kill_chrome 已经确保端口可用
    if is_port_open(port):
        print(f"✅ 端口 {port} 已开启，准备接管现有浏览器实例...")
    else:
        print(f"🌐 正在启动带代理配置的新浏览器实例...")
        command = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--proxy-server=http://{PROXY_ADDR}:{PROXY_PORT}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            subprocess.Popen(command)
            time.sleep(3)  # 给浏览器充足的启动时间
            return True
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False


async def check_all_proxies():
    """
    批量验证所有代理IP（调用你写的 get_proxy_pool）
    """
    print("=" * 70)
    print("开始验证所有代理IP能否访问：https://mobile.pinduoduo.com/")
    print("=" * 70)

    is_valid = await test_single_proxy()

    if is_valid:
        print("✅ 代理可用！")
    else:
        print("❌ 代理不可用！")

    return True


# 直接运行即可
if __name__ == "__main__":
    # 批量验证所有代理
    asyncio.run(check_all_proxies())