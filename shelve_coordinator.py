import sys
import os
import time
import uiautomator2 as u2

sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')
sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce/collect_data/pdd/uiautomator2_spider/uiautomator2_to_db')

from config import ip_port

from collect_data.pdd.uiautomator2_spider.uiautomator2_to_db.uiautomator2_url_spider_backup import (
    initialize_check_data,
    get_pending_products,
    start_shelving_process as collect_products,
    logger as spider_logger
)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, 'shelving_goofish_phone_spiderphone'))
from shelving_goofish_phone_spiderphone.auto_shelve_manager import main_manager as shelve_to_xianyu


def run_collection_phase(device):
    print("\n" + "=" * 60)
    print("📦 阶段1: 商品数据采集")
    print("=" * 60)

    spider_logger.info("🔄 正在初始化商品校验表...")
    initialize_check_data()

    spider_logger.info("📦 正在获取待采集数据列表...")
    pending_list = get_pending_products()
    spider_logger.info(f"📋 待处理商品数量: {len(pending_list)}")

    if pending_list:
        collect_products(pending_list, device)
        print("✅ 商品数据采集完成")
        return True
    else:
        print("✨ 无待采集商品，跳过采集阶段")
        return False


def run_shelving_phase(device):
    print("\n" + "=" * 60)
    print("🛒 阶段2: 闲鱼商品上架")
    print("=" * 60)

    shelve_to_xianyu(device)
    print("✅ 闲鱼上架流程完成")


def run_coordinator():
    print("=" * 60)
    print("🔄 闲鱼商品自动化流程启动")
    print("=" * 60)

    print(f"\n📱 正在连接设备: {ip_port}")
    device = u2.connect(ip_port)
    print("✅ 设备连接成功")

    run_collection_phase(device)

    run_shelving_phase(device)

    print("\n" + "=" * 60)
    print("🎉 所有自动化流程执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    run_coordinator()