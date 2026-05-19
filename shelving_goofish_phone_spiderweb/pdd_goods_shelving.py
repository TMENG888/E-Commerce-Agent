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
            cursor.execute("SELECT sales_desc FROM goods_descriptions WHERE goods_id = %s", (goods_id,))
            res = cursor.fetchone()
            return res['sales_desc'] if res else ""
    finally:
        conn.close()


def get_specs_from_mongo(goods_id):
    """从 MongoDB 获取规格信息"""
    client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
    col = client[MONGO_CONFIG["db"]][MONGO_CONFIG["collection"]]
    cursor = col.find({"goods_id": goods_id})
    items = list(cursor)

    specs_map = {}
    exclude = ["goods_id", "price", "original_sku", "_id"]
    for item in items:
        for k, v in item.items():
            if k not in exclude:
                if k not in specs_map: specs_map[k] = set()
                specs_map[k].add(v)
    return specs_map


def sync_folder_to_phone(device, local_folder, remote_dir, label="图片"):
    """
    通用同步函数
    :param device: uiautomator2 的设备实例 d
    :param local_folder: 本地文件夹路径
    :param remote_dir: 手机端目标路径
    :param label: 用于日志区分的标签（如 '商品图', '规格图'）
    """
    # --- 1. 清空并准备远程目录 ---
    device.shell(f"rm -rf {remote_dir}*")
    device.shell(f"mkdir -p {remote_dir}")
    print(f"🧹 [{label}] 已清空远程目录: {remote_dir}")

    # 获取有效图片
    local_images = [img for img in os.listdir(local_folder) if img.lower().endswith(('.jpg', '.png', '.jpeg'))]
    total_count = len(local_images)

    if total_count == 0:
        print(f"⚠️ [{label}] 本地没有可推送的图片")
        return

    # --- 2. 异步监听器 ---
    def monitor_progress(device, expected_count):
        print("🔍 启动图片推送监听器...")
        uploaded_count = 0
        while uploaded_count < expected_count:
            # 统计手机端已存在的图片数量
            res = device.shell(f"ls {remote_dir} | grep IMG_ | wc -l")
            uploaded_count = int(res.output.strip() if res.output.strip() else 0)
            print(f"进度: {uploaded_count}/{expected_count}")
            if uploaded_count >= expected_count:
                break
            time.sleep(1)  # 每秒检查一次
        print("✅ 监听器确认：所有图片已推送成功。")

    monitor_thread = threading.Thread(target=monitor_progress, args=(device, total_count))
    monitor_thread.daemon = True
    monitor_thread.start()

    # --- 3. 重命名并推送 ---
    for img in local_images:
        local_path = os.path.join(local_folder, img)

        # 生成随机文件名：IMG_ + 5位随机数 + 原后缀
        ext = os.path.splitext(img)[1]
        random_num = random.randint(10000, 99999)
        new_name = f"IMG_{random_num}{ext}"

        target_path = remote_dir + new_name
        device.push(local_path, target_path)

    # --- 4. 刷新媒体库 ---
    # 注意：Android 高版本建议扫描整个文件夹
    device.shell(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_dir}")
    print(f"✅ [{label}] 推送并刷新完成")


# --- 自动化填写流程 ---
def start_shelving_process(goods_id, d):
    # # 1. 准备数据
    description = get_desc_from_mysql(goods_id)
    specs = get_specs_from_mongo(goods_id)

    # 本地图片路径
    base_local_path = r"C:\Users\31193\Pictures"

    # 1. 处理上架图
    item_local = os.path.join(base_local_path, "商品上架图", str(goods_id))
    item_remote = "/sdcard/Pictures/Gallery/owner/上架商品图/"
    sync_folder_to_phone(d, item_local, item_remote, label="商品上架图")

    # 2. 处理规格图
    spec_local = os.path.join(base_local_path, "商品规格图", str(goods_id))
    spec_remote = f"/sdcard/Pictures/Gallery/owner/{goods_id}/"
    sync_folder_to_phone(d, spec_local, spec_remote, label="商品规格图")

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

    # 4. 选择图片
    d(description="添加图片").click()
    time.sleep(1)
    d(description="所有文件").click()
    time.sleep(1)
    d.xpath('//android.widget.ImageView[contains(@content-desc, "上架商品图")]').click()
    time.sleep(2)

    # 逻辑：在相册中找到对应文件夹（此处需根据闲鱼具体UI路径调整）
    while d(description="选择").exists:
        d(description="选择", instance=0).click()
    d(descriptionContains="下一步").click()
    time.sleep(2)

    while d(description="完成").exists:
        d(description="完成").click()
        time.sleep(5)

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
                d(description="添加规格类型").click()
                d(className="android.widget.EditText", instance=1).click()

            time.sleep(1)
            d.send_keys(spec_name)
            d.press("enter")

            # 填写具体规格值
            # 注意：这里需要根据 Y 轴偏移逻辑点击每个输入框，参考你 playwright_collect_to_db.py 的循环
            start_y = 550
            for v_idx, val in enumerate(list(values)):
                if (total_spec_types == 2 and total_spec_values >= 9) or total_spec_values >= 11:
                    d.swipe_ext("up", scale=0.7)
                    time.sleep(3)

                    # 具体规格框
                    d.click(159, 2019)
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
    target_id = "61490906507"
    ip_port = "172.20.10.4:38487"

    d = u2.connect(ip_port)
    start_shelving_process(target_id, d)