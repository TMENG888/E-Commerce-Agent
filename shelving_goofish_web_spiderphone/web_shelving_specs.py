import json
import math
import os
import sys
import time
import socket
import subprocess
import pymysql
from playwright.sync_api import sync_playwright
from pymongo import MongoClient

COOKIE_PATH = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_cookies.json"

MYSQL_CONFIG = {
    'host': 'localhost', 
    'user': 'root', 
    'password': '123456', 
    'database': 'pdd_db', 
    'charset': 'utf8mb4',
    'autocommit': True
}

MONGO_CONFIG = {
    "host": "localhost", 
    "port": 27017, 
    "db": "Goofish", 
    "collection": "Goods_Specification"
}

PUBLISH_URL = "https://seller.goofish.com/?site=COMMONPRO#/seller-item/publish"
GOODS_MANAGE_URL = "https://seller.goofish.com/?site=COMMONPRO#/seller-item/goods-manage"


def is_port_open(port):
    """检查本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def ensure_chrome_running():
    """确保 Chrome 浏览器以调试模式运行"""
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
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            subprocess.Popen(command)
            time.sleep(3)
            print("✅ 浏览器启动成功")
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False
    return True


def get_pending_shelve_list():
    """
    查询数据校验全通过(check_all_data=1)
    但尚未执行上架操作(check_shelf=0) 的商品 ID 列表
    """
    conn = pymysql.connect(**MYSQL_CONFIG)
    pending_ids = []
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT goods_id FROM goods_check_data 
            WHERE check_all_data = 1 AND check_shelf = 0
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            pending_ids = [row[0] for row in results]
    except Exception as e:
        print(f"❌ 查询待上架列表失败: {e}")
    finally:
        conn.close()
    return pending_ids


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


def calculate_xianyu_price(cost_price):
    """
    全新连续数学模型：根据拼多多成本价，动态计算符合闲鱼买家心理学的销售价
    目标：低价位保持高利润率，200元高价位时利润额控制在20元左右
    """
    if cost_price <= 0:
        return 0.0

    # 1. 【核心改动】使用反比例根号函数计算连续的动态利润率
    # 成本越低，利润率越高；成本越高，利润率平滑下降
    dynamic_profit_rate = 0.05 + (1.5 / math.sqrt(cost_price))

    # 2. 限制利润率的安全边界（最低不低于 8%，最高不超过 45%）
    dynamic_profit_rate = max(0.08, min(0.45, dynamic_profit_rate))

    # 3. 带入数学公式，把 1.6% 的平台扣点转嫁给买家
    # 销售价 = (成本 * (1 + 动态利润率)) / (1 - 0.016)
    raw_price = (cost_price * (1 + dynamic_profit_rate)) / (1 - 0.016)

    # 4. 闲鱼心理学微调（本元.8 -> 本元.9 -> 下一元.8）
    base_integer = math.floor(raw_price)

    for tail in [0.8, 0.9, 1.8]:
        predicted_price = base_integer + tail
        if predicted_price >= raw_price:
            return round(predicted_price, 1)

    return round(raw_price, 1)


def get_specs_from_mongo(goods_id):
    """
    从 MongoDB 获取规格信息 (返回完整的规格字典)
    新结构: {"规格名": {"Specification": "精简名", "price": 35.99, "path": "...", "spec_id": 1}}
    返回: [
        {"spec_name": "规格名", "Specification": "精简名", "price": 35.99, "path": "...", "spec_id": 1},
        ...
    ]
    """
    client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
    col = client[MONGO_CONFIG["db"]][MONGO_CONFIG["collection"]]

    doc = col.find_one({"goods_id": str(goods_id)})

    if not doc or "sku" not in doc:
        print(f"⚠️ 未找到 goods_id 为 {goods_id} 的规格数据")
        return []

    sku_content = doc["sku"]

    if isinstance(sku_content, dict):
        specs_list = []
        for spec_name, spec_data in sku_content.items():
            origin_price = spec_data.get("price", 0)
            xianyu_price = calculate_xianyu_price(origin_price)
            specs_list.append({
                "spec_name": spec_name,
                "Specification": spec_data.get("Specification", ""),
                "price": xianyu_price,
                "origin_price": origin_price,
                "path": spec_data.get("path", ""),
                "spec_id": spec_data.get("spec_id", 0)
            })
        return specs_list
    else:
        print(f"❌ sku 字段格式异常，预期为字典，实际为: {type(sku_content)}")
        return []


def mark_goods_as_listed(goods_id):
    """更新商品的上架状态"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE `goods_check_data` SET `check_shelf` = 1 WHERE `goods_id` = %s"
            cursor.execute(sql, (goods_id,))
        conn.commit()
        print(f"✅ 商品 {goods_id} 已标记为『已上架』")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ 更新状态失败: {e}")
        return False
    finally:
        conn.close()


def find_page_by_url(context, target_url):
    """在浏览器上下文中查找包含指定 URL 的页面"""
    for page in context.pages:
        if target_url in page.url:
            return page
    return None


def get_or_create_publish_page(context):
    """获取或创建发布页面"""
    # 首先检查是否有发布成功页面（包含 publish/success?itemId=）
    for page in context.pages:
        if "publish/success?itemId=" in page.url:
            print("🎉 找到发布成功页面，点击'再发一件'...")
            try:
                another_btn = page.locator('button.btnCommon--osVweuJI.btnPrimary--qbzKZHtf').filter(has_text='再发一件')
                if another_btn.count() > 0:
                    another_btn.click()
                    time.sleep(5)
                    return page
            except Exception as e:
                print(f"⚠️ 点击'再发一件'失败: {e}")
    
    # 然后检查是否有普通发布页面
    publish_page = find_page_by_url(context, "#/seller-item/publish")
    if publish_page:
        print("🔄 找到已打开的发布页面，刷新页面...")
        publish_page.reload()
        time.sleep(3)
        return publish_page
    
    # 最后创建新页面
    print("🌐 未找到发布页面，创建新页面...")
    new_page = context.new_page()
    new_page.goto(PUBLISH_URL)
    time.sleep(5)
    return new_page


def get_or_create_goods_manage_page(context):
    """获取或创建商品管理页面"""
    goods_manage_page = find_page_by_url(context, GOODS_MANAGE_URL)
    if goods_manage_page:
        print("🔄 找到已打开的商品管理页面，刷新页面...")
        goods_manage_page.reload()
        time.sleep(3)
        return goods_manage_page
    else:
        print("🌐 未找到商品管理页面，创建新页面...")
        new_page = context.new_page()
        new_page.goto(GOODS_MANAGE_URL)
        time.sleep(5)
        return new_page


def shelve_single_goods(page, goods_id):
    """上架单个商品，返回是否上架成功"""
    print(f"\n📦 处理商品: {goods_id}")
    publish_success = False

    description = get_desc_from_mysql(goods_id)
    specs = get_specs_from_mongo(goods_id)

    print(f"   ├── 描述长度: {len(description)}")
    print(f"   └── 规格数量: {len(specs)}")

    if description:
        print("📝 填写商品描述...")
        desc_input = page.locator('[data-placeholder="描述一下宝贝的品牌型号、货品来源..."]')
        desc_input.click()
        time.sleep(1)
        page.keyboard.type(description)
        time.sleep(2)

    if len(specs) != 1:
        print("🔧 填写规格信息...")
        
        add_btn = page.locator('button.addBtn--aeORl7oU')
        if add_btn.count() > 0:
            add_btn.click()
            time.sleep(2)
        else:
            print("   ⚠️ 未找到添加规格按钮")
            return False

        select_div = page.locator('#itemProperties_0_propertyName')
        if select_div.count() > 0:
            select_div.click()
            time.sleep(2)
        else:
            print("   ⚠️ 未找到规格类型选择框")
            return False

        color_option = page.locator('div.ant-select-item-option-content', has_text='颜色')
        if color_option.count() > 0:
            color_option.click()
        else:
            color_option = page.locator('div.ant-select-item', has_text='颜色')
            if color_option.count() > 0:
                color_option.click()
            else:
                print("   ⚠️ 未找到颜色选项")
                return False
        time.sleep(1)

        for idx, spec in enumerate(specs):
            spec_name = spec.get("Specification", "") or spec.get("spec_name", "")
            spec_price = spec.get("price", 0)
            print(f"      └── 规格{idx+1}: {spec_name}, 价格: {spec_price}")
            
            input_selector = f'input[id="itemProperties_0_propertyValues_{idx}_propertyValue"]'
            input_element = page.locator(input_selector)
            
            if input_element.count() > 0:
                input_element.click()
                time.sleep(0.5)
                input_element.fill(spec_name)
                time.sleep(1)
            else:
                print(f"      ⚠️ 未找到第 {idx+1} 个规格值输入框")

            price_input = page.locator(f'input[id="itemSkuList_{idx}_price"]')
            if price_input.count() > 0:
                price_input.click()
                time.sleep(0.5)
                price_input.fill(str(spec_price))
                time.sleep(0.5)
            else:
                price_inputs = page.locator('span.ant-input-affix-wrapper input.ant-input')
                if price_inputs.count() > idx:
                    price_inputs.nth(idx).click()
                    time.sleep(0.5)
                    price_inputs.nth(idx).fill(str(spec_price))
                    time.sleep(0.5)
                else:
                    print(f"      ⚠️ 未找到第 {idx+1} 个价格输入框")

            stock_input = page.locator(f'input[id="itemSkuList_{idx}_quantity"]')
            if stock_input.count() > 0:
                stock_input.click()
                time.sleep(0.5)
                stock_input.fill("9")
                time.sleep(0.5)
            else:
                stock_inputs = page.locator('input[placeholder="0"][min="0"]')
                if stock_inputs.count() > idx:
                    stock_inputs.nth(idx).click()
                    time.sleep(0.5)
                    stock_inputs.nth(idx).fill("3")
                    time.sleep(0.5)
                else:
                    print(f"⚠️ 未找到第 {idx+1} 个库存输入框")

        # 上传规格图片的逻辑
        print("🖼️  开始上传规格图片...")
        upload_divs = page.locator('div.inputImgUpload--XnhX4Utt')
        upload_count = upload_divs.count()
        
        for idx, spec in enumerate(specs):
            if idx >= upload_count:
                print(f"⚠️ 图片上传元素数量不足，只有 {upload_count} 个，跳过第 {idx+1} 个规格的图片上传")
                continue
                
            image_path = spec.get("path", "")
            if not image_path or not os.path.exists(image_path):
                print(f"⚠️ 规格 {idx+1} 的图片路径不存在或为空: {image_path}")
                continue
                
            print(f"      └── 上传规格 {idx+1} 的图片: {os.path.basename(image_path)}")
            
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    upload_divs.nth(idx).click()
                file_chooser = fc_info.value
                file_chooser.set_files(image_path)
                print(f"      ✅ 图片上传成功: {os.path.basename(image_path)}")
                time.sleep(2)
            except Exception as e:
                print(f"      ❌ 图片上传失败: {e}")
    else:
        print("   └── 该商品仅有一个规格，填写售价、原价和库存")
        
        if len(specs) == 1:
            spec = specs[0]
            spec_price = spec.get("price", 0)
            original_price = round(spec_price * 2.5, 2)
            
            print(f"      └── 规格价格: {spec_price}, 原价: {original_price}, 库存: 3")
            
            # 填写售价
            try:
                price_inputs = page.locator('span.ant-input-affix-wrapper input.ant-input')
                if price_inputs.count() > 0:
                    price_inputs.first.click()
                    time.sleep(0.5)
                    price_inputs.first.fill(str(spec_price))
                    time.sleep(0.5)
                    print(f"      ✅ 已填写售价: {spec_price}")
                else:
                    print(f"      ⚠️ 未找到售价输入框")
            except Exception as e:
                print(f"      ❌ 填写售价失败: {e}")
            
            # 填写原价（可能需要查找第二个价格输入框或特定选择器）
            try:
                # 尝试查找所有价格输入框，第二个通常是原价
                all_price_inputs = page.locator('input[placeholder="0.00"], input[min="0"]')
                if all_price_inputs.count() >= 2:
                    all_price_inputs.nth(1).click()
                    time.sleep(0.5)
                    all_price_inputs.nth(1).fill(str(original_price))
                    time.sleep(0.5)
                    print(f"      ✅ 已填写原价: {original_price}")
            except Exception as e:
                print(f"      ⚠️ 填写原价失败: {e}")
            
            # 填写库存
            try:
                stock_inputs = page.locator('input[placeholder="1"], input[placeholder="0"][min="0"]')
                if stock_inputs.count() > 0:
                    stock_inputs.first.click()
                    time.sleep(0.5)
                    stock_inputs.first.fill("3")
                    time.sleep(0.5)
                    print(f"      ✅ 已填写库存: 3")
                else:
                    print(f"      ⚠️ 未找到库存输入框")
            except Exception as e:
                print(f"      ❌ 填写库存失败: {e}")



    # 上传商品主图的逻辑
    print("🖼️开始上传商品主图...")
    main_image_path = r"C:\Users\31193\Pictures\test\O1CN01fbcC6223vhUHxqTwH_!!4611686018427383414-0-fleamarket.jpg_790x10000Q90.jpg_.webp"

    if os.path.exists(main_image_path):
        try:
            main_upload_div = page.locator('div.upload-item--VvK_FTdU')
            if main_upload_div.count() > 0:
                print(f"   └── 上传主图: {os.path.basename(main_image_path)}")

                with page.expect_file_chooser(timeout=10000) as fc_info:
                    main_upload_div.click()
                file_chooser = fc_info.value
                file_chooser.set_files(main_image_path)
                print(f"   ✅ 主图上传成功: {os.path.basename(main_image_path)}")
                time.sleep(3)
            else:
                print("   ⚠️ 未找到主图上传元素")
        except Exception as e:
            print(f"   ❌ 主图上传失败: {e}")
    else:
        print(f"   ⚠️ 主图文件不存在: {main_image_path}")

    # 点击发布按钮
    print("🚀 准备发布商品...")
    try:
        publish_btn = page.locator('button.ant-btn-primary').filter(has_text='发布')
        if publish_btn.count() > 0:
            is_disabled = publish_btn.get_attribute('disabled')
            if is_disabled:
                print("⚠️ 发布按钮当前为禁用状态，请检查必填项是否已填写")
            else:
                publish_btn.click()
                print("✅ 已点击发布按钮")
                publish_success = True
                time.sleep(3)
        else:
            print("⚠️ 未找到发布按钮")
    except Exception as e:
        print(f"❌ 点击发布按钮失败: {e}")

    return publish_success


def unlist_last_goods(page):
    """下架刚刚发布的商品，返回是否下架成功"""
    print("\n🔻 准备下架刚刚发布的商品...")
    
    try:
        unlist_btn = page.locator('a.operaBtn--Ur1hcVNu').filter(has_text='下架')
        print("📍执行下架操作")
        unlist_btn.first.click()
        time.sleep(2)

        # 点击确定按钮
        page.evaluate("""() => {
            document.querySelectorAll('.ant-btn-primary')[1].click();
        }""")
        print("✅ 商品下架成功")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"   ❌ 下架商品失败: {e}")
        return False


def run(goods_id=None):
    pending_list = []
    
    if goods_id:
        pending_list = [goods_id]
    else:
        pending_list = get_pending_shelve_list()

    if not pending_list:
        print("✨ 暂无符合上架条件的商品")
        return

    print(f"📋 检测到 {len(pending_list)} 个待上架商品: {pending_list}")

    print("\n🔗 检查浏览器状态...")
    if not ensure_chrome_running():
        return

    with sync_playwright() as p:
        print("\n🔗 连接浏览器...")
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 无法连接到浏览器: {e}")
            return

        context = browser.contexts[0]

        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        context.add_cookies(cookies)

        for gid in pending_list:
            print(f"\n" + "="*60)
            print(f"开始处理商品: {gid}")
            print("="*60)
            
            publish_success = True
            unlist_success = False
            
            # 步骤1: 获取或创建发布页面，上架商品
            publish_page = get_or_create_publish_page(context)
            time.sleep(1)
            publish_success = shelve_single_goods(publish_page, gid)
            
            if publish_success:
                print("\n✅ 上架操作成功")
                # 步骤2: 获取或创建商品管理页面，下架商品
                goods_manage_page = get_or_create_goods_manage_page(context)
                unlist_success = unlist_last_goods(goods_manage_page)
            else:
                print("\n❌ 上架操作失败，跳过下架步骤")
            
            # 只有上架和下架都成功才更新数据库
            if publish_success and unlist_success:
                mark_goods_as_listed(gid)
                print(f"\n✅ 商品 {gid} 上架并下架流程完成，已更新数据库")
            else:
                print(f"\n⚠️ 商品 {gid} 流程未完全成功，不更新数据库")

        print("\n🎉 所有商品处理完成")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        goods_id = sys.argv[1]
        print(f"📌 手动指定商品 ID: {goods_id}")
        run(goods_id)
    else:
        print("🔄 自动获取待上架商品列表...")
        run()
