import os
import shutil
import socket
import subprocess
import time

import pymysql


class Base:
    def __init__(self):
        self.GOOFISH_DB_CONFIG = {
            'host': 'localhost',
            'user': 'root',
            'password': '123456',
            'database': 'goofish_db',
            'charset': 'utf8mb4'
        }

        self.PDD_DB_CONFIG = {
            'host': 'localhost',
            'user': 'root',
            'password': '123456',
            'database': 'pdd_db',
            'charset': 'utf8mb4'
        }

        self.BASE_IMAGE_FOLDER = r"C:\Users\31193\Pictures\business_image"

    def cleanup_profile(self):
        """物理清理 Chrome 缓存目录，实现状态隔离"""
        user_data_dir = r"C:\selenium\automation_profile"

        # 1. 强制杀死所有 Chrome 进程，否则文件夹被占用无法删除
        try:
            subprocess.run('taskkill /F /IM chrome.exe', shell=True, capture_output=True)
            time.sleep(1)
        except Exception:
            pass

        # 2. 删除特定的缓存文件夹,我们只需删除指纹关联最强的部分
        folders_to_remove = [
            'Default/Cache',
            'Default/Code Cache',
            'Default/Local Storage',
            'Default/IndexedDB',
            'Default/Network/Cookies'
        ]

        for folder in folders_to_remove:
            path = os.path.join(user_data_dir, folder.replace('/', os.sep))
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    print(f"🧹 已清理缓存: {folder}")
                except Exception as e:
                    print(f"⚠️ 清理 {folder} 失败: {e}")

    def is_port_open(self, port):
        """检查本地端口是否已被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 设置超时时间，避免长时间阻塞
            s.settimeout(1)
            return s.connect_ex(('127.0.0.1', port)) == 0

    def ensure_chrome_running(self, proxy_url=None):
        port = 9222
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        user_data_dir = r"C:\selenium\automation_profile"

        if proxy_url and self.is_port_open(port):
            print("🔄 发现代理切换需求，正在关闭旧浏览器实例...")
            subprocess.run('taskkill /F /IM chrome.exe', shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            time.sleep(1)

        if self.is_port_open(port):
            print(f"✅ 端口 {port} 已开启，准备接管现有浏览器实例...")
        else:
            print(f"🌐 端口 {port} 未开启，正在启动新浏览器实例...")
            command = [
                chrome_path,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",  # 跳过首次运行引导
                "--no-default-browser-check"  # 跳过默认浏览器检查
            ]
            try:
                # 使用 Popen 后，给浏览器一点点启动时间
                subprocess.Popen(command)
                time.sleep(2)
            except Exception as e:
                print(f"❌ 启动失败: {e}")
                return False
        return True

    def get_proxy_pool(self):
        """
        从 proxy_pool 表获取所有IP代理
        返回格式：["http://ip:port", "http://ip:port", ...]
        """
        try:
            conn = pymysql.connect(**self.PDD_DB_CONFIG)
            cursor = conn.cursor()

            # 查询所有IP:PORT（按采集时间最新排序）
            cursor.execute("SELECT ip_port FROM proxy_pool ORDER BY collect_time DESC")
            results = cursor.fetchall()

            # 组装成标准代理池格式
            proxy_list = [f"{row[0]}" for row in results]

            return proxy_list

        except Exception as e:
            print(f"❌ 获取代理池失败：{e}")
            return []  # 出错返回空列表

        finally:
            if 'conn' in locals():
                conn.close()
