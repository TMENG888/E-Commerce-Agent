import glob
import time
import json
import ast
import os
import re
import sys
import uiautomator2 as u2
import pymysql
import requests
import base64
import logging
from typing import List
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from pymongo import MongoClient, ASCENDING
from zai import ZhipuAiClient
from openai import OpenAI
import subprocess

sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')
from config import ip_port


def setup_logger():
    """
    配置日志管理模块
    - 日志文件按当天日期命名，存放在 logs 目录下
    - 同时输出到控制台和文件
    - 每次运行追加日志到当天文件
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"spider_{today}.log")

    logger = logging.getLogger("uiautomator2_spider")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()

# 数据库连接配置 (从您的 Selected_products_db.py 中提取)
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

# MongoDB 配置
MONGO_CONFIG = {
    "host": "localhost",
    "port": 27017,
    "db": "Goofish",
    "collection": "Goods_Specification"
}

headers = {
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Origin': 'https://uiauto.dev',
    'Pragma': 'no-cache',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
    'sec-ch-ua': '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

api_key = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"


class ProductAI:
    def __init__(self):
        self.client = ZhipuAiClient(api_key=api_key)
        self.model_name = "GLM-4.6V-FlashX"

    def _encode_image(self, image_path: str):
        with open(image_path, "rb") as image_file:
            return f"data:image/jpeg;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"

    def describe_product(self, image_paths: List[str]):
        if not image_paths:
            return "无图片可识别"

        content_list = []
        for path in image_paths:
            img_b64 = self._encode_image(path)
            content_list.append({
                "type": "image_url",
                "image_url": {"url": img_b64}
            })

        content_list.append({
            "type": "text",
            "text": "你是一个电商专家。请分析这些商品图片，提取出详细的商品描述。要求包含：商品名称、核心卖点、外观设计、功能参数。用简洁的列表格式输出。"
        })

        try:
            logger.info("大模型正在提取商品图信息...")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": content_list}]
            )

            logger.info("提取商品图信息成功！！！")

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"识别异常: {str(e)}")
            return f"识别异常: {str(e)}"

    def process_with_ai(self, goods_id, sku_data):
        """
        调用大模型解析 SKU 并生成精简的 Specification
        输入：新结构的 sku 数据 {规格名: {"Specification": "", "price": 18.9, "path": "...", "spec_id": 1}}
        输出：直接更新 sku_data 中的 Specification 字段
        """
        max_retries = 3

        # 提取规格信息供 AI 处理
        specs_list = []
        for spec_name, spec_data in sku_data.items():
            specs_list.append({
                "spec_id": spec_data.get("spec_id", 0),
                "original_name": spec_name
            })

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个电商数据综合专家。你必须严格遵守以下规则：\n"
                    "1. 输入是一个包含规格信息的 JSON 列表。\n"
                    "2. 输出是一个 JSON 列表，每个元素包含 spec_id 和 Specification 字段。\n"
                    "3. Specification 是规格名的精简版本，必须缩减到 12 个汉字以内。\n"
                    "4. 去除冗余修饰（如：含胶垫、适配、尺寸等）。\n"
                    "5. 保持 spec_id 不变，与输入一一对应。\n"
                    "6. 输出格式必须是纯 JSON 数组，不要包含其他内容。"
                )
            },
            {
                "role": "user",
                "content": f"请处理以下规格数据，生成精简的 Specification：{specs_list}"
            },
            {
                "role": "assistant",
                "content": """
                [
                    {"spec_id": 1, "Specification": "黑单键"},
                    {"spec_id": 2, "Specification": "白键鼠"},
                    {"spec_id": 3, "Specification": "黑键鼠"}
                ]
                """
            }
        ]

        for attempt in range(max_retries):
            try:
                logger.info(f"正在尝试第 {attempt + 1} 次处理...")

                client = OpenAI(api_key="sk-1acc01f0f60d46b4a09905339c58b622", base_url="https://api.deepseek.com")
                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    temperature=0.1,
                    messages=messages
                )
                content = response.choices[0].message.content

                # 解析返回的 JSON 列表
                try:
                    result = json.loads(content)
                    if isinstance(result, list):
                        # 直接更新内存中的 sku_data 字典
                        for item in result:
                            if "spec_id" in item and "Specification" in item:
                                spec_id = item["spec_id"]
                                specification = item["Specification"]
                                # 找到对应的规格并更新
                                for spec_name, spec_data in sku_data.items():
                                    if spec_data.get("spec_id") == spec_id:
                                        sku_data[spec_name]["Specification"] = specification
                                        logger.info(f"✅ 更新规格 {spec_name} 的 Specification: {specification}")
                        return sku_data
                except json.JSONDecodeError:
                    # 尝试其他解析方式
                    result = self.parse_refined_skus(content)
                    if isinstance(result, list):
                        for item in result:
                            if isinstance(item, dict) and "spec_id" in item and "Specification" in item:
                                spec_id = item["spec_id"]
                                specification = item["Specification"]
                                for spec_name, spec_data in sku_data.items():
                                    if spec_data.get("spec_id") == spec_id:
                                        sku_data[spec_name]["Specification"] = specification
                                        logger.info(f"✅ 更新规格 {spec_name} 的 Specification: {specification}")
                        return sku_data

            except Exception as e:
                logger.error(f"❌ 运行异常: {repr(e)}")
                time.sleep(1)
                continue

        return sku_data

    def parse_refined_skus(self, raw_response):
        if not raw_response:
            return {}

        # 1. 深度清洗：移除所有可能的 Markdown 包装和多余的空白符
        # 移除 ```json, ```, """, ''', 以及首尾的引号
        clean_json = str(raw_response).strip()
        clean_json = re.sub(r'^(?:```json|```|"""json|"""|\'\'\'json|\'\'\'|json)', '', clean_json, flags=re.I)
        clean_json = re.sub(r'(?:```|"""|\'\'\')$', '', clean_json).strip()

        # 特别处理：如果字符串首尾依然有引号，剥掉它
        if (clean_json.startswith('"') and clean_json.endswith('"')) or \
                (clean_json.startswith("'") and clean_json.endswith("'")):
            clean_json = clean_json[1:-1].strip()

        try:
            # 尝试标准 JSON 解析
            return json.loads(clean_json)
        except json.JSONDecodeError:
            try:
                # 尝试 Python 字面量解析（处理单引号字典）
                return ast.literal_eval(clean_json)
            except Exception as e:
                # 最后的倔强：手动替换单引号为双引号再试一次
                try:
                    # 注意：这种替换很危险，仅作为保底逻辑
                    fix_json = clean_json.replace("'", '"')
                    return json.loads(fix_json)
                except:
                    logger.error(f"❌ 所有解析方法均失败。原始内容预览: {clean_json[:50]}")
                    # 返回原始数据防止流程彻底中断，但建议返回空字典 {}
                    return {}

    def generate_xianyu_copy(self, title, sku_info_text, image_info_text):
        """
        根据商品标题、规格信息和图片识别描述，生成闲鱼爆款文案
        """
        try:
            # Messages
            messages = [
                {
                    "role": "system",
                    "content": f"""
                    你是一位专业的电商文案撰写专家，擅长将商品信息转化为具有吸引力的爆款销售文案。你的任务是根据用户提供的商品标题、规格详情和外观描述，生成一篇符合目标案例风格的文案。目标案例风格特点：开头用感叹句突出促销信息（如包邮、清仓特价，全新未拆封），短句列举核心卖点（如参数、功能、使用场景），然后补充操作说明或个性化提示，最后用标签（#）和客服互动语结尾。文案语言要口语化、有感染力，多用感叹号但不要用emoji，需突出性价比和实用性。注意：用户提供的变量包含商品标题，规格详情（多个款式选项），外观与场景描述（核心卖点、设计、功能参数）。在生成文案时，需从这些变量中提取关键信息，但每个变量在文案中只能使用一次，而且以闲鱼第一人称(不要出现客服小姐姐等等)。
        
                    输出格式要求:
                    纯文本
                    """
                },
                {
                    "role": "assistant",
                    "content": f"""
                    包邮！清仓特价未拆封机械手感键盘静音电竞游戏办公电脑有线通用接口
        
                    26键无冲！悬浮按键，打字不累手腕，按压无压力，字符白色背光，时尚简约大方～科技感十足，键盘质感在线！可闭眼入～
        
                    办公室宿舍游戏都可以用！轻音不扰人！字符背光白天晚上使用都超级方便！
        
                    开灯按太阳键，呼吸灯按fn + 太阳键，三档亮度可调
                    有视频教程，需要看敲击视频也私信小姐姐！！！
        
                    紫色白色粉色蓝色键鼠套装模认搭配白色鼠标
                    黑灰黑蓝光橙光彩光默认黑色鼠标
        
                    有其他需求的和客服说！！！
        
                    #键盘 #电脑键盘
        
                    拍下后24小时内发货！有问题可直接咨询小姐姐～#电竞电脑装备 ，#键盘 #电脑键盘
                    """
                },
                {
                    "role": "user",
                    "content": f"""
                    根据以下商品信息生成一篇爆款销售文案：
                    商品标题：{title}
                    规格详情：{sku_info_text}
                    商品外观与场景描述：{image_info_text}
                    """
                }
            ]

            # --- 请求 AI ---
            client = OpenAI(api_key="sk-1acc01f0f60d46b4a09905339c58b622", base_url="https://api.deepseek.com")
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                temperature=0.1,
                messages=messages
            )
            content = response.choices[0].message.content

            cleaned_text_01 = re.sub(r'^[^\S\n]+', '', content.strip(), flags=re.MULTILINE)

            cleaned_text = cleaned_text_01.replace('*', '').replace('#', '')

            return cleaned_text
        except Exception as e:
            logger.error(f"❌ 闲鱼文案生成失败: {e}")
            return ""


def initialize_check_data():
    """
    初始化校验表：
    1. 获取 selected_products 中 detail_url 不为空的记录
    2. 解析出 goods_id
    3. 在 goods_check_data 中插入初始记录（校验位默认为 0）
    """
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. 获取所有有效的 URL 记录
        fetch_sql = ("""SELECT detail_url FROM selected_products WHERE detail_url IS NOT NULL AND DATE(created_at) = CURDATE()""")
        cursor.execute(fetch_sql)
        products = cursor.fetchall()

        if not products:
            logger.info("ℹ️ selected_products 表中无待初始化数据")
            return

        # 2. 准备初始化 goods_check_data
        init_sql = """
        INSERT IGNORE INTO `goods_check_data` 
            (goods_id, check_title, check_sku_info, check_image_info, 
             check_sale_copy, check_local_img, check_sku_mongo, check_all_data)
        VALUES (%s, 0, 0, 0, 0, 0, 0, 0)
        """

        count = 0
        for item in products:
            gid = extract_goods_id(item['detail_url'])
            if gid:
                cursor.execute(init_sql, (gid,))
                count += cursor.rowcount

        conn.commit()
        logger.info(f"✅ 成功初始化 {count} 条商品校验记录到 goods_check_data")
        conn.close()
    except Exception as e:
        logger.error(f"❌ 初始化校验表失败: {e}")

def ensure_uiauto_service():
    """检查服务是否可用，不可用则尝试启动"""
    check_url = "http://127.0.0.1:20242/api/android/"
    try:
        requests.get(check_url, timeout=2)
        logger.info("✅ uiauto.dev 服务已在运行")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logger.warning("⚠️ 检测到 uiauto.dev 服务未启动，正在尝试拉起...")
        # 替换为你电脑上 uiauto.dev 的实际安装路径
        exe_path = r"E:\Scripts\uiauto.dev.exe"

        if os.path.exists(exe_path):
            # 使用 Popen 后台运行，不阻塞主程序
            subprocess.Popen([exe_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            logger.info("🚀 服务启动命令已发送，等待 5 秒初始化...")
            time.sleep(5)  # 给服务启动留出缓冲时间
        else:
            logger.error(f"❌ 找不到执行文件: {exe_path}，请检查路径。")


def get_hierarchy_safe(ip_port, headers):
    """获取界面层级数据，带重试机制"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f'http://127.0.0.1:20242/api/android/{ip_port}/hierarchy'
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
        except requests.exceptions.ConnectionError:
            logger.warning(f"🚨 连接失败 (尝试 {attempt + 1}/{max_retries})，准备拉起服务...")
            ensure_uiauto_service()
            time.sleep(2)

    logger.error("❌ 无法恢复 uiauto.dev 连接，请手动检查。")
    return None

def get_pending_products():
    """
    关联查询：从 selected_products 获取 URL，
    但仅筛选 goods_check_data 中 check_all_data 为 0 的商品
    """
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        # 使用 JOIN 确保只采集需要补齐数据的商品
        sql = """
        SELECT p.id, p.detail_url 
        FROM selected_products p
        JOIN goods_check_data c ON SUBSTRING_INDEX(SUBSTRING_INDEX(p.detail_url, 'goods_id=', -1), '&', 1) = c.goods_id
        WHERE c.check_all_data = 0
        AND p.detail_url IS NOT NULL
        """
        # 注意：上述 SQL 中的 goods_id 提取逻辑较为硬核，如果 URL 格式复杂，建议先在 python 处理
        cursor.execute(sql)
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"❌ 读取待处理列表失败: {e}")
        return []


def update_collected_status(product_id):
    """更新数据库收藏状态"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        sql = "UPDATE selected_products SET is_collected = 1 WHERE id = %s"
        cursor.execute(sql, (product_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ 数据库状态已更新：ID {product_id} -> 已收藏")
    except Exception as e:
        logger.error(f"❌ 更新数据库失败: {e}")


def extract_sku(data):
    # --- 1. 递归拍平 (保持原样) ---
    flat_nodes = []
    def flatten_tree(node):
        props = node.get("properties", {})
        if props.get("text", "").strip():
            flat_nodes.append(props)
        for child in node.get("children", []):
            flatten_tree(child)
    flatten_tree(data)

    sku_data = {}
    current_category = None

    # --- 2. 正则准备 (保持原样) ---
    category_pattern = re.compile(r'^[选择]*[\u4e00-\u9fa5]{1,5}[类别式号型]?$')
    junk_pattern = re.compile(r'卖完|优惠|仅剩|促|热销|已抢|已拼|库存|送达|限购|评价|回购|马上|立即|支付|直降|专享|满减|券|平台|百亿补贴')
    option_blacklist = ["1", "列表", "大图", "确定", "关闭", "立即购买", "加入购物车"]

    # --- 3. 核心遍历 ---
    for prop in flat_nodes:
        raw_text = prop.get("text", "").strip()
        text_for_match = re.sub(r'[【】]', '', raw_text)
        is_clickable = prop.get("clickable") == "true"

        if not is_clickable and len(text_for_match) <= 10 and "¥" not in text_for_match:
            if category_pattern.match(text_for_match) and not junk_pattern.search(text_for_match):
                current_category = text_for_match
                if current_category not in sku_data:
                    sku_data[current_category] = set() # 使用 set 自动去重
            continue

        if current_category and is_clickable:
            if raw_text in option_blacklist or len(raw_text) == 0:
                continue
            # 直接添加字符串到集合中
            clean_text = re.sub(r'\s*¥\s*\d+(\.\d+)?', '', raw_text).strip()

            sku_data[current_category].add(clean_text)

    # --- 4. 转换格式并清理 ---
    # 将 set 转换为 list 以便输出，同时剔除空分类
    final_sku = {k: list(v) for k, v in sku_data.items() if len(v) > 0}

    return final_sku


def smart_merge_skus(total, current):
    """
    智能合并规格字典
    1. 自动识别并纠正错误的噪声键名（如"店铺"纠正为"适用型号"）
    2. 自动去重新增的规格值
    """
    for cur_key, cur_values in current.items():
        matched_key = None
        cur_val_set = set(cur_values)

        # --- 策略 A：内容重合度判定 (解决"店铺"vs"适用型号"问题) ---
        for exist_key, exist_values in total.items():
            exist_val_set = set(exist_values)

            # 计算重合度：当前页面的值有多少比例已经存在于总表中
            # 如果当前分类里有超过 30% 的规格在之前的某个分类里出现过，就认为它们是同一类
            if not cur_val_set.isdisjoint(exist_val_set):
                intersection = cur_val_set.intersection(exist_val_set)
                overlap_ratio = len(intersection) / len(cur_val_set)

                if overlap_ratio > 0.3:  # 阈值可调
                    matched_key = exist_key
                    break

        # --- 策略 B：合并数据 ---
        if matched_key:
            # 发现是同一个分类，合并并去重
            logger.info(f"🔗 发现重复规格内容，将『{cur_key}』的数据合并至旧分类『{matched_key}』")
            total[matched_key] = list(set(total[matched_key]) | cur_val_set)
        else:
            # 确实是新分类，直接添加
            if cur_key in total:
                total[cur_key] = list(set(total[cur_key]) | cur_val_set)
            else:
                total[cur_key] = list(cur_val_set)

    return total


def get_collection():
    """获取 MongoDB 集合"""
    client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
    db = client[MONGO_CONFIG["db"]]
    collection = db[MONGO_CONFIG["collection"]]

    # 确保 goods_id 有唯一索引（加速查询）
    collection.create_index([("goods_id", ASCENDING)], unique=True)

    return collection


def extract_goods_id(url):
    """提取 goods_id"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if 'goods_id' in params:
        return params['goods_id'][0]

    match = re.search(r'goods_id=(\d+)', url)
    if match:
        return match.group(1)
    return None


def save_sku_to_mongo(goods_id, total_result):
    """
    存储或更新 SKU 数据（新结构）
    新结构：{规格名: {"Specification": "...", "price": 18.9, "path": "...", "spec_id": 1}}
    """
    collection = get_collection()

    doc = {
        "_id": goods_id,
        "goods_id": goods_id,
        "sku": total_result,
        "updated_at": datetime.now(timezone.utc)
    }

    result = collection.update_one(
        {"_id": goods_id},
        {"$set": doc},
        upsert=True
    )

    if result.upserted_id:
        logger.info(f"✅ 新增商品 SKU 数据，goods_id: {goods_id}")
    else:
        logger.info(f"🔄 更新商品 SKU 数据，goods_id: {goods_id}")


def update_sku_specification(goods_id, spec_id, specification):
    """
    更新单个规格的 Specification 字段
    """
    collection = get_collection()
    
    # 查找规格名
    doc = collection.find_one({"_id": goods_id})
    if doc and "sku" in doc:
        for spec_name, spec_data in doc["sku"].items():
            if spec_data.get("spec_id") == spec_id:
                # 更新 Specification 字段
                collection.update_one(
                    {"_id": goods_id, f"sku.{spec_name}": {"$exists": True}},
                    {"$set": {f"sku.{spec_name}.Specification": specification}}
                )
                logger.info(f"✅ 更新规格 {spec_name} 的 Specification: {specification}")
                return True
    
    logger.warning(f"⚠️ 未找到 spec_id={spec_id} 的规格")
    return False


def add_sku_item(goods_id, spec_name, price, image_path, spec_id):
    """
    添加单个 SKU 项到 MongoDB（在采集过程中逐步添加）
    """
    collection = get_collection()
    
    sku_item = {
        "Specification": "",
        "price": price,
        "path": image_path,
        "spec_id": spec_id
    }
    
    result = collection.update_one(
        {"_id": goods_id},
        {"$set": {
            f"sku.{spec_name}": sku_item,
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    
    if result.upserted_id:
        logger.info(f"✅ 新增商品 {goods_id} 及规格 {spec_name}")
    else:
        logger.info(f"🔄 更新商品 {goods_id} 的规格 {spec_name}")
    
    return True

    return goods_id


def get_sku_by_goods_id(goods_id):
    """通过 goods_id 检索 SKU 数据"""
    collection = get_collection()
    doc = collection.find_one({"goods_id": str(goods_id)})

    if doc:
        return doc.get("sku", {})
    return None


def format_sku_to_text(total_sku):
    """
    严谨计算 SKU 数量并格式化文本
    """
    # 如果传入的是字符串（JSON），先转回字典
    if isinstance(total_sku, str):
        import json
        total_sku = json.loads(total_sku)

    # 1. 直接获取键值对总数（这就是最严谨的 SKU 数量）
    total_count = len(total_sku)

    # 2. 提取简短的规格文本（用于展示）
    # 建议只取每个 Key 的后半段，避开冗长的品牌前缀
    keys = total_sku.keys()
    short_names = []
    for key in keys:
        # 尝试提取 | 之后的内容，如果没有 | 则取最后 10 个字
        parts = key.split('｜')
        name = parts[-1] if len(parts) > 1 else key[-10:]
        short_names.append(name.strip())

    formatted_text = f"款式：{'、'.join(short_names)}"

    return total_count, formatted_text

def sync_sku_to_mysql(goods_id, title=None, total_sku=None, image_info=None, sale_copy=None):
    """
    将 SKU 数据和标题同步到 MySQL 的 goods_des 表

    Args:
        goods_id: 商品ID
        title: 商品标题
        total_sku: smart_merge_skus 返回的合并后规格字典
        image_info: 图片信息（可选，dict/list）
        sale_copy: 闲鱼文案（可选）
    """
    connection = pymysql.connect(**MYSQL_CONFIG)

    try:
        with connection.cursor() as cursor:
            # 使用 upsert 策略：存在则更新，不存在则插入
            sql = """
            INSERT INTO `goods_desc`
                (`goods_id`, `title`, `sku_info`, `image_info`, `sale_copy`, `created_at`)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `title` = VALUES(`title`),
                `sku_info` = VALUES(`sku_info`),
                `image_info` = VALUES(`image_info`),
                `sale_copy` = VALUES(`sale_copy`),
                `created_at` = VALUES(`created_at`)
            """

            cursor.execute(sql, (
                goods_id,
                title,
                total_sku,
                image_info,
                sale_copy,
                datetime.now()
            ))

            connection.commit()
            logger.info(f"✅ 商品 {goods_id} 的 SKU 数据已同步至 MySQL")

    except Exception as e:
        connection.rollback()
        logger.error(f"❌ 同步失败: {e}")
        raise
    finally:
        connection.close()


def perform_deep_quality_check(goods_id, image_dir):
    """
    深度核验：检查 MySQL、MongoDB 及本地文件是否存在且有效
    """
    results = {
        "check_title": 0, "check_sku_info": 0, "check_image_info": 0,
        "check_sale_copy": 0, "check_local_img": 0, "check_sku_mongo": 0
    }

    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        # 使用 DictCursor 方便通过键名读取字段
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 校验 MySQL 中的 goods_desc 数据内容
            sql_check = "SELECT title, sku_info, image_info, sale_copy FROM goods_desc WHERE goods_id = %s"
            cursor.execute(sql_check, (goods_id,))
            row = cursor.fetchone()

            if row:
                # 检查字段是否非空且长度符合基本逻辑
                if row['title'] and len(row['title'].strip()) > 0: results["check_title"] = 1
                if row['sku_info'] and len(row['sku_info'].strip()) > 0: results["check_sku_info"] = 1
                if row['image_info'] and len(row['image_info'].strip()) > 0: results["check_image_info"] = 1
                # 文案通常较长，设定最小长度校验
                if row['sale_copy'] and len(row['sale_copy'].strip()) > 30: results["check_sale_copy"] = 1

        # 2. 校验本地图片文件 (是否存在 .jpg 结尾的文件)
        if os.path.exists(image_dir):
            imgs = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if len(imgs) > 0:
                results["check_local_img"] = 1

        # 3. 校验 MongoDB 原始 SKU 记录
        try:
            collection = get_collection()
            if collection.find_one({"goods_id": str(goods_id)}):
                results["check_sku_mongo"] = 1
        except Exception as mongo_err:
            logger.warning(f"⚠️ MongoDB 校验异常: {mongo_err}")

        # 4. 计算全流程成功标志
        # 排除 check_shelf (它是后续流程)，其余 6 项必须全部为 1
        core_checks = [results[k] for k in
                       ["check_title", "check_sku_info", "check_image_info", "check_sale_copy", "check_local_img",
                        "check_sku_mongo"]]
        all_success = 1 if all(core_checks) else 0

        # 5. 更新校验结果至 goods_check_data 表
        upsert_sql = """
        INSERT INTO `goods_check_data`
            (goods_id, check_title, check_sku_info, check_image_info, check_sale_copy, check_local_img, check_sku_mongo, check_all_data)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            check_title=VALUES(check_title), check_sku_info=VALUES(check_sku_info),
            check_image_info=VALUES(check_image_info), check_sale_copy=VALUES(check_sale_copy),
            check_local_img=VALUES(check_local_img), check_sku_mongo=VALUES(check_sku_mongo),
            check_all_data=VALUES(check_all_data)
        """
        with conn.cursor() as cursor:
            cursor.execute(upsert_sql, (
                goods_id, results["check_title"], results["check_sku_info"],
                results["check_image_info"], results["check_sale_copy"],
                results["check_local_img"], results["check_sku_mongo"], all_success
            ))
        conn.commit()
        return all_success

    except Exception as e:
        logger.error(f"❌ 质量校验过程执行失败: {e}")
        return 0
    finally:
        if 'conn' in locals() and conn: conn.close()


def extract_price(price_str):
    """提取价格数字（优先匹配价格符号后面的数字）"""
    # 优先匹配 ¥ 或 $ 或 元 后面的数字
    match = re.search(r'[¥$元]\s*(\d+\.?\d*)', price_str)
    if match:
        return float(match.group(1))
    
    # 如果没有价格符号，匹配最后一个数字（通常价格在最后）
    matches = re.findall(r'(\d+\.?\d*)', price_str)
    if matches:
        return float(matches[-1])
    
    return None

def start_shelving_process(products, device=None):
    """执行遍历收藏流程"""
    if not products:
        logger.info("📭 没有需要处理的商品。")
        return

    # 初始化图片同步器
    image_sync = None
    try:
        sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')
        from mobile_image_sync import MobileImageSync
        image_sync = MobileImageSync(ip_port)
        logger.info("✅ 图片同步器初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 图片同步器初始化失败: {e}")

    # 启动拼多多
    logger.info("🚀 启动拼多多...")
    device.app_stop("com.xunmeng.pinduoduo")
    device.app_start("com.xunmeng.pinduoduo")
    device.set_input_ime(True)
    time.sleep(5)  # 给首页加载留出时间

    for p_id, url in products:
        final_skus = {}
        goods_id = extract_goods_id(url)
        if not goods_id:
            raise ValueError(f"无法从 URL 提取 goods_id: {url}")
        logger.info(f"🔎 正在处理商品 ID: {goods_id}, URL: {url}")

        try:
            # 1. 点击搜索框 (坐标参考您提供的 545, 162)
            device.click(545, 162)
            time.sleep(1.5)

            # 2. 清空旧搜索内容
            device(resourceId="com.xunmeng.pinduoduo:id/pdd", className="android.widget.EditText").clear_text()

            # 3. 输入详情页 URL 并搜索
            device.send_keys(url)
            time.sleep(1)
            device(text="搜索").click()
            time.sleep(3)  # 等待商品详情页加载

            # 4. 点击收藏按钮 (根据您之前确定的坐标 193, 2259)
            if device(text="收藏").exists:
                device.click(193, 2259)
                logger.info(f"💖 已点击收藏按钮")
                time.sleep(2)
                # 5. 更新数据库状态
                update_collected_status(p_id)
            elif device(text="已收藏").exists:
                update_collected_status(p_id)

            # 关闭悬浮视频
            close_button = device(resourceId="com.xunmeng.pinduoduo:id/iv_float_window_close")
            if close_button.exists():
                close_button.click()

            # 采集标题数据
            title = device.xpath('//android.view.ViewGroup[@resource-id="com.xunmeng.pinduoduo:id/tv_title"]').info['contentDescription']
            logger.info(f"📝 商品标题: {title}")

            # 准备商品图目录
            save_dir = rf"C:\Users\31193\Pictures\商品图\{goods_id}"

            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                logger.info(f"📁 目录已创建: {save_dir}")

            # 获取商品图
            device.swipe(540, 1800, 540, 400, steps=10)
            time.sleep(1)
            device.swipe(540, 1800, 540, 400, steps=20)
            time.sleep(3)
            count = 1

            while True:
                # 点击图片
                if count == 1:
                    device(index=0).click()

                    # 检查是否为第一张照片，决定是否回滚操作
                    page_text = device(className="android.widget.TextView", textMatches=r"\d+/\d+").get_text()
                    current, total = map(int, page_text.split('/'))
                    for _ in range(current-1):
                        device.swipe(200, 1000, 900, 1000, steps=10)
                        time.sleep(0.5)

                # 生成截图文件名（例如：截图_1.jpg）
                time.sleep(1)
                file_path = os.path.join(save_dir, f"step_{count}.jpg")
                device.screenshot(file_path)
                count += 1

                page_text = device(className="android.widget.TextView", textMatches=r"\d+/\d+").get_text()
                current, total = map(int, page_text.split('/'))

                if current >= total:
                    logger.info(f"✅ 已到达最后一张图片，停止采集。")
                    break

                device.swipe(900, 1000, 200, 1000, steps=10)

            device(description="返回").click()

            image_files = glob.glob(os.path.join(save_dir, "*.jpg"))

            # 实例化并调用大模型 (假设你已经初始化了 ai_client)
            ai_tool = ProductAI()
            image_desc = ai_tool.describe_product(image_files)

            # 点击唤醒sku面板
            device.click(730, 2300)
            time.sleep(3)

            # 点击规格图片
            device.xpath('//android.view.ViewGroup[2]/android.widget.LinearLayout[1]/android.view.ViewGroup[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.RelativeLayout[1]/android.view.ViewGroup[1]/android.view.View[1]').click()

            sku_data_map = {}
            first_label = True
            spec_id_counter = 1

            while True:
                page_text = None
                if device(textContains="/").exists(timeout=1):
                    # 检查当前图片索引和总图片数
                    elements = device(textContains="/")
                    for ele in elements:
                        txt = ele.get_text()
                        # 核心判断：必须包含 / 且分割后两边都是纯数字
                        parts = txt.split("/", 1)
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            page_text = txt
                            current = int(parts[0])
                            total = int(parts[1])
                            break
                    if first_label == True and total != 1:
                        for _ in range(current - 1):
                            device.swipe(200, 1000, 900, 1000, steps=10)
                        sku_desc = device.xpath(
                            '//android.widget.HorizontalScrollView//android.widget.TextView[1]').get_text()
                        first_label = False

                        current = 1
                    elif first_label == False and total == 2:
                        sku_desc = device.xpath(
                            '//android.widget.HorizontalScrollView//android.widget.TextView[2]').get_text()
                    else:
                        sku_desc = device.xpath(
                            '//android.widget.HorizontalScrollView//android.widget.TextView[2]').get_text()
                else:
                    sku_desc = device.xpath(
                        '//android.widget.HorizontalScrollView//android.widget.TextView[1]').get_text()

                # 价格定位（假设位置固定）
                if device.xpath(
                    '//android.widget.FrameLayout[4]/android.view.ViewGroup[1]/android.widget.TextView[1]').exists:
                    sku_price = device.xpath(
                        '//android.widget.FrameLayout[4]/android.view.ViewGroup[1]/android.widget.TextView[1]').get_text()
                else:
                    sku_price = device.xpath(
                        '//android.widget.FrameLayout[3]/android.view.ViewGroup[1]/android.widget.TextView[1]').get_text()

                # --- 🚀 核心存储步骤 ---
                # 只保留价格数字
                clean_price = extract_price(sku_price)
                # 使用新结构：{ "规格名": {"Specification": "", "price": 18.9, "path": "", "spec_id": 1} }
                sku_data_map[sku_desc] = {
                    "Specification": "",
                    "price": clean_price,
                    "path": "",
                    "spec_id": spec_id_counter
                }
                spec_id_counter += 1
                logger.info(f"📥 暂存数据: 款式={sku_desc}, 价格={clean_price}, spec_id={spec_id_counter-1}")

                # 3. 保存图片逻辑
                device.long_click(491, 1133, duration=0.5)
                time.sleep(0.5)
                device(text="保存图片").click()
                time.sleep(2)

                # 4. 异步同步当前规格的图片到电脑（不阻塞主线程），并传入 sku_data_map 更新 path
                if image_sync:
                    try:
                        image_sync.sync_single_spec_image(goods_id, sku_desc, sku_data_map=sku_data_map)
                    except Exception as e:
                        logger.warning(f"⚠️ 单张图片同步失败: {e}")

                if not page_text or current == total:
                    time.sleep(1)
                    device.click(491, 1133)
                    break
                elif current != total:
                    device.swipe(900, 1000, 200, 1000, steps=10)
                    time.sleep(0.5)

            # 等待所有异步图片同步线程完成
            if image_sync:
                logger.info("⏳ 等待图片同步线程完成...")
                time.sleep(3)
            
            # 清理手机端剩余图片
            if image_sync:
                try:
                    image_sync.clear_phone_pdd_images()
                except Exception as e:
                    logger.warning(f"⚠️ 清理图片失败: {e}")

            # 转化sku为文本并计算sku的数量
            num, sku_text = format_sku_to_text(sku_data_map)

            # 将字典转为文本描述传给 AI（sku_data_map 已经是新结构）
            refined_skus = ai_tool.process_with_ai(goods_id, sku_data_map)
            save_sku_to_mongo(goods_id, refined_skus)

            sale_desc = ai_tool.generate_xianyu_copy(title, sku_text, image_desc)
            sync_sku_to_mysql(goods_id, title, sku_text, image_desc, sale_desc)

            logger.info(f"🧐 正在执行数据质量校验: {goods_id}")
            is_valid = perform_deep_quality_check(goods_id, save_dir)

            if is_valid:
                logger.info(f"🌟 商品 {goods_id} 采集质量合格：数据已入库，图片已保存。")
            else:
                logger.warning(f"🚩 商品 {goods_id} 校验未通过：请检查 goods_check_data 表定位缺失字段。")

            if device(description="关闭").exists():
                device(description="关闭").click()

            if device(text="先去逛逛").exists:
                device(text="先去逛逛").click()

            # 6. 返回搜索页准备下一个
            device(description="返回", index=1).click()
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"⚠️ 处理商品 {p_id} 时发生错误: {e}")
            if device(description="关闭").exists():
                device(description="关闭").click()

            if device(text="先去逛逛").exists:
                device(text="先去逛逛").click()

            # 6. 返回搜索页准备下一个
            device(description="返回", index=1).click()
            time.sleep(1.5)
            continue


if __name__ == "__main__":
    logger.info("🚀 爬虫程序启动")

    # 1. 第一步：初始化校验表 (将 URL 映射为 ID 并预设为 0)
    logger.info("🔄 正在初始化商品校验表...")
    initialize_check_data()

    # 2. 连接设备
    device = u2.connect(ip_port)
    logger.info(f"✅ 设备连接成功")

    # 3. 获取任务列表 (仅获取 check_all_data = 0 的商品)
    logger.info("📦 正在获取待采集数据列表...")
    pending_list = get_pending_products()
    logger.info(f"📋 待处理商品数量: {len(pending_list)}")

    # 4. 执行采集流程
    if pending_list:
        start_shelving_process(pending_list, device)
    else:
        logger.info("✨ 所有商品数据已达标，无需重复采集。")