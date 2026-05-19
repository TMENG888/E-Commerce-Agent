import pymysql
import time
import uiautomator2 as u2
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')
from pdd_goods_shelving import start_shelving_process
from config import ip_port

# 数据库配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}


def fetch_pending_goods():
    """
    查询符合条件的商品：
    1. check_all = 1 (所有采集和图片校验已通过)
    2. check_shelf = 0 (尚未执行上架)
    """
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
            SELECT goods_id FROM goods_check_results 
            WHERE check_all = 1 AND check_shelf = 0
            """
            cursor.execute(sql)
            return [row['goods_id'] for row in cursor.fetchall()]
    finally:
        conn.close()


def update_shelf_status(goods_id):
    """上架成功后，更新数据库状态"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE goods_check_results SET check_shelf = 1 WHERE goods_id = %s"
            cursor.execute(sql, (goods_id,))
            print(f"✅ 数据库已同步：商品 {goods_id} 上架状态已更新为 1")
    finally:
        conn.close()


def main_manager(device):
    print("🚀 启动自动化上架监控程序...")

    # 1. 获取待上架列表
    pending_list = fetch_pending_goods()

    if not pending_list:
        print("✨ 暂无符合上架条件的商品（需 check_all=1 且 check_shelf=0）。")
        return

    print(f"📋 检测到 {len(pending_list)} 个待上架商品: {pending_list}")

    # 2. 遍历并执行上架
    for gid in pending_list:
        print(f"\n▶️ 正在处理商品: {gid}")
        try:
            # 调用你提供的上架逻辑
            success = start_shelving_process(gid, device)

            if success:
                # 3. 只有上架成功才更新状态
                update_shelf_status(gid)
                print(f"✅ 商品ID为{gid}已存入草稿箱，请自行确认并完成发布。")
            else:
                print(f"⚠️ 商品 {gid} 上架脚本运行失败，跳过状态更新。")

        except Exception as e:
            print(f"❌ 处理商品 {gid} 时出现异常: {e}")

        # 每个商品之间稍微停顿，避免手机操作过快导致卡顿
        time.sleep(5)


if __name__ == "__main__":
    device = u2.connect(ip_port)
    main_manager(device)