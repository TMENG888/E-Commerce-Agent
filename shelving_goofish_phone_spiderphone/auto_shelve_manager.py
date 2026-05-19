import pymysql
import time
import uiautomator2 as u2
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')
from single_spec_goods_shelving import start_shelving_process
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

def get_pending_shelve_list():
    """
    查询数据校验全通过(check_all_data=1)
    但尚未执行上架操作(check_shelf=0) 的商品 ID 列表
    """
    conn = pymysql.connect(**MYSQL_CONFIG)
    pending_ids = []
    try:
        with conn.cursor() as cursor:
            # SQL 查询语句：筛选校验成功且未上架的商品
            sql = """
            SELECT goods_id FROM goods_check_data 
            WHERE check_all_data = 1 AND check_shelf = 0
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            # 提取 goods_id 列表
            pending_ids = [row[0] for row in results]
    except Exception as e:
        print(f"❌ 查询待上架列表失败: {e}")
    finally:
        conn.close()
    return pending_ids


def mark_goods_as_listed(goods_id):
    """
    更新商品的上架状态（同时更新描述表和校验表）
    """
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 2. 更新 goods_check_data 表（新增逻辑）
            sql_check = "UPDATE `goods_check_data` SET `check_shelf` = 1 WHERE `goods_id` = %s"
            cursor.execute(sql_check, (goods_id,))

        conn.commit()
        print(f"✅ 商品 {goods_id} 已在描述表和校验表中标记为『已上架』")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ 更新状态失败: {e}")
        return False
    finally:
        conn.close()

def main_manager(device):
    print("🚀 启动自动化上架监控程序...")

    # 1. 获取待上架列表
    pending_list = get_pending_shelve_list()

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
                mark_goods_as_listed(gid)
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