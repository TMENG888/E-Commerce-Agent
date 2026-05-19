import random
import threading

import uiautomator2 as u2
import time
import os
import pymysql
from pymongo import MongoClient

# --- 配置部分 ---
# 1. 数据库连接
MYSQL_CONFIG = {'host': 'localhost', 'user': 'root', 'password': '123456', 'database': 'pdd_db', 'charset': 'utf8mb4'}
MONGO_CONFIG = {"host": "localhost", "port": 27017, "db": "Goofish", "collection": "Goods_Specification"}


# --- 核心功能函数 ---
def get_desc_from_mysql(goods_id):
    """从 MySQL 获取商品描述文案"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT sale_copy FROM goods_desc WHERE goods_id = %s", (goods_id,))
            res = cursor.fetchone()
            return res['sale_copy'] if res else ""
    finally:
        conn.close()


def get_specs_from_mongo(goods_id):
    """从 MongoDB 获取规格信息 (适配嵌套的 sku 字段)"""
    client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
    col = client[MONGO_CONFIG["db"]][MONGO_CONFIG["collection"]]

    # 查找指定 goods_id 的文档
    doc = col.find_one({"goods_id": goods_id})

    if not doc or "sku" not in doc:
        print(f"⚠️ 未找到 goods_id 为 {goods_id} 的规格数据")
        return {}

    specs_map = {}
    # 直接遍历嵌套在 'sku' 键下的内容
    sku_content = doc["sku"]

    for category, options in sku_content.items():
        # 如果获取到的是列表（如示例中所示），直接转换为 set
        if isinstance(options, list):
            specs_map[category] = set(options)
        else:
            # 如果是单个字符串值，则创建 set 并添加
            if category not in specs_map:
                specs_map[category] = set()
            specs_map[category].add(options)

    return specs_map


# --- 自动化填写流程 ---
def start_shelving_process(goods_id, d):
    # # 1. 准备数据
    description = get_desc_from_mysql(goods_id)
    specs = get_specs_from_mongo(goods_id)

    # 2. 打开闲鱼并进入发布页
    d.app_stop("com.taobao.idlefish")
    d.app_start("com.taobao.idlefish")
    time.sleep(3)
    d(descriptionContains="卖闲置").click()
    d(descriptionContains="发闲置").click()
    d.watcher.when("放弃").click()
    d.watcher.start()

    # 切换输入法
    d.set_input_ime(True)  # 开启 FastInput
    time.sleep(3)

    # 3. 填写描述和标题
    d(descriptionContains="描述一下宝贝").click()
    d.send_keys(description)
    time.sleep(1)

    # 5. 填写规格 (核心修改逻辑)
    # 向上滑动找到规格入口
    time.sleep(3)
    if specs.items():
        # --- 初始化统计计数器 ---
        total_spec_types = 0
        total_spec_values = 0

        # 滚动查找并点击唤起商品规格
        d.swipe(540, 2150, 540, 500, duration=0.7)
        target_spec = d(descriptionStartsWith="商品规格")

        while True:
            if target_spec.wait(timeout=2):
                target_spec.click()
                time.sleep(7)
                break
            else:
                d.swipe(540, 1532, 540, 500, duration=0.5)

        # 遍历 MongoDB 里的规格维度（如：颜色、尺寸）
        for idx, (spec_name, values) in enumerate(specs.items()):
            total_spec_types += 1

            # 点击添加规格类型
            if idx == 0:
                d.click(967, 414)
                d.click(967, 414)
            else:
                if total_spec_values >= 10:
                    d.swipe_ext("up", scale=0.7)
                d(description="添加规格类型").click()
                time.sleep(1)
                if d(className="android.widget.EditText", instance=1).count == 1:
                    d(className="android.widget.EditText", instance=1).click()
                else:
                    d(className="android.widget.EditText").click()

            time.sleep(1)
            d.send_keys(spec_name)
            d.press("enter")

            # 填写具体规格值
            # 注意：这里需要根据 Y 轴偏移逻辑点击每个输入框，参考你 playwright_collect_to_db.py 的循环
            start_y = 550
            for v_idx, val in enumerate(list(values)):
                if total_spec_values >= 11 and not (total_spec_types == 2 and total_spec_values >= 9):
                    d.swipe_ext("up", scale=0.7)
                    time.sleep(3)

                    # 点击规格值的位置并输入值
                    d.click(151, 1880)
                    d.send_keys(val)
                    d.press("enter")
                    time.sleep(1)
                elif total_spec_types == 2 and total_spec_values >= 9:
                    d.swipe_ext("up", scale=0.7)
                    time.sleep(3)

                    # 点击规格值的位置并输入值
                    d.click(151, 2023)
                    d.send_keys(val)
                    d.press("enter")
                    time.sleep(1)
                else:
                    total_spec_values += 1
                    if idx == 0:
                        curr_y = start_y + (v_idx * 150)
                    else:
                        first_spec_num = len(list(specs.items())[0][1]) - 1
                        curr_y = start_y + (first_spec_num * 150) + 500 + (v_idx * 150)
                    d.click(150, curr_y)
                    d.send_keys(val)
                    d.press("enter")
                    time.sleep(1)

        # 下一步设置价格
        d(descriptionContains="下一步 设置价格").click()
        time.sleep(2)

        # 点击批量设置价格和库存
        d.click(190, 398)
        time.sleep(2)

        # 点击全选
        d.click(190, 398)
        time.sleep(2)

        # 点击批量设置价格和库存
        d.click(692, 2236)
        time.sleep(0.5)

        # 点击填写默认价格
        d(description="3").click()
        time.sleep(2)

        # 点击填写默认库存
        d(className="android.widget.EditText", instance=1).click()
        d(description="9").click()
        time.sleep(2)

        # 点击确定按钮
        d(description="确定").click()
        time.sleep(2)

        # 点击完成按钮
        d(description="完成").click()
        time.sleep(2)

    # 点击存入草稿箱
    d(description="存草稿").click()
    time.sleep(2)

    d.app_stop("com.taobao.idlefish")
    return True


# 执行
if __name__ == "__main__":
    target_id = "879352975580"
    ip_port = "10.140.128.153:38593"

    d = u2.connect(ip_port)
    start_shelving_process(target_id, d)