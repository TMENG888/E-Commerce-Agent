import glob
import time
import json
import os
import re
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
import subprocess


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

    def process_with_ai(self, sku_desc):
        """调用大模型解析 SKU 并精简改写规格"""
        max_retries = 3

        # 优化后的 System Prompt
        # Messages
        messages = [
            {
                "role": "system",
                "content": f"""
                你是一位商品规格整理专家。你的任务是根据用户提供的商品规格文本，将其整理为结构化的JSON格式。具体要求如下：
                1. 原始文本中包含多个规格维度（如颜色、版本等），你需要识别并合并为最多2个维度。
                2. 每个具体的规格值必须压缩到10个汉字以内，例如'油画海浪耳机【耳塞式五代pro2顶配版】'应简化为'油画海浪【顶配】'。
                3. 如果原始规格中包含了版本信息（如'顶配版'、'终极版'），请将其作为颜色名称的一部分，用【】或（）标注，例如'黄可达鸭【终极】'。
                4. 输出格式必须为JSON，包含两个数组，数组名根据实际维度命名（如'颜色'、'套餐'）。
                5. 注意：原始变量{sku_desc}中包含了所有商品规格的文本，请严格基于该文本进行分析，不要添加或删除任何信息。
                6. 规格值不得出现重复的值，请勿重复规格值。

                输出格式要求:
                JSON
        """
            },
            {
                "role": "assistant",
                "content": """
                {
                        "颜色": [
                      "黑色【升级款】",
                      "黑色（基础款）",
                      "绿色【升级款】",
                      "绿色（基础款）",
                      "蓝色（基础款）",
                      "白色（基础款）",
                      "白色【升级款】",
                      "粉色【升级款】",
                      "粉色（基础款）",
                      "蓝色【升级款】"
                    ],
                    "套餐":[
                      "套餐1",
                      "套餐2",
                      "套餐3"
                    ]
                  }
            """
            },
            {
                "role": "user",
                "content": f"请根据以下商品规格文本，整理为结构化的JSON格式，要求合并为最多2个维度，每个规格值压缩到10个汉字以内，且不得出现重复：{sku_desc}"
            }
        ]

        for attempt in range(max_retries):
            try:
                logger.info(f"正在尝试第{attempt + 1}次SKU信息结构化转换...")

                response = self.client.chat.completions.create(
                    model="GLM-4-Flash-250414",
                    messages=messages,
                    temperature=0.1,
                    thinking={"type": "disabled"}
                )

                content = response.choices[0].message.content

                return content
            except Exception as e:
                logger.error(f"❌ AI 解析失败 (Attempt {attempt + 1}): {e}")
                if "rate limit" in str(e).lower():
                    time.sleep(20)
                continue
        return None

    def parse_refined_skus(self, raw_response):
        # 如果是带有 """json ... """ 的字符串，用正则提取中间的内容
        if isinstance(raw_response, str):
            # 移除 ```json 或 """json 等标记
            clean_json = re.sub(r'^(?:"""json|```json|json|["\']{3})', '', raw_response)
            clean_json = re.sub(r'(?:"""|```|["\']{3})$', '', clean_json).strip()
            try:
                return json.loads(clean_json)
            except json.JSONDecodeError:
                logger.error("❌ 无法解析 JSON 字符串")
                return None
        return raw_response

    def validate_and_clean_skus_dict(self, sku_dict):
        """
        针对字典格式的校验：
        1. 先去重每个规格类型下的重复值（保留顺序）
        2. 如果某个 Key 对应的 List 长度 <= 1，则删除该 Key

        输入示例: {"颜色": ["红", "蓝", "红"], "规格": ["74键", "129键", "74键"]}
        输出示例: {"颜色": ["红", "蓝"], "规格": ["74键", "129键"]}

        输入示例: {"颜色": ["红", "红"], "规格": ["74键", "129键"]}
        输出示例: {"规格": ["74键", "129键"]}  # 颜色去重后只剩"红"，被删除
        """
        if not sku_dict or not isinstance(sku_dict, dict):
            return sku_dict

        # 第一步：去重每个规格值（保持原有顺序）
        for key, values in sku_dict.items():
            if isinstance(values, list):
                # 使用 dict.fromkeys 保持顺序的去重
                unique_values = list(dict.fromkeys(values))
                if len(unique_values) != len(values):
                    logger.info(f"🧹 规格校验：维度 '{key}' 发现重复值，已去重 ({len(values)} -> {len(unique_values)})")
                sku_dict[key] = unique_values

        # 第二步：找出所有只有一个规格值的维度并删除
        keys_to_remove = [
            key for key, values in sku_dict.items()
            if isinstance(values, list) and len(values) <= 1
        ]

        for key in keys_to_remove:
            logger.info(f"🧹 规格校验：维度 '{key}' 下仅有单一值，已执行剔除。")
            del sku_dict[key]

        return sku_dict

    def generate_xianyu_copy(self, title, sku_info_text, image_info_text):
        """
        根据商品标题、规格信息和图片识别描述，生成闲鱼爆款文案
        """
        try:
            # 此时 title 对应表中的 title
            # sku_info_text 对应格式化后的 SKU 文本
            # image_info_text 对应大模型识别出的图片描述文本

            response = self.client.chat.completions.create(
                model="GLM-4-Flash-250414",
                messages=[
                    {
                        "role": "system",
                        "content": f"""
                    你是一位电商爆款文案撰写专家，擅长将商品信息转化为高转化率的销售文案。你的任务是根据用户提供的商品标题、规格详情和外观描述，生成一篇结构清晰、卖点突出、语言有感染力的销售文案，但不要出现emoji符号。文案风格要模仿目标案例：开头用【】突出核心卖点，接着用感叹句制造紧迫感，然后分模块展示必抢理由、功能实测、操作细节、其他细节和售后保障，最后用标签和话题词收尾。注意：变量 {title} 包含商品标题，{sku_info_text} 包含规格详情，{image_info_text} 包含外观与场景描述（含商品名称、核心卖点、外观设计、功能参数）。每个变量在文案中只使用一次，但可以在不同段落中引用其包含的多个信息点。
    
                    输出格式要求:
                    纯文本
                    """
                    },
                    {
                        "role": "assistant",
                        "content": f"""
                    【全新包邮】灰原哀侧刻原厂透光键帽 全套PBT热升华 适配ROG夜魔美加狮wooting
    
                    公司活动剩的！亏本清仓价甩！全新未拆封！错过血亏！
    
                    全新！全新宝贝！只要能拍就有货！
                    标价就是卖价 一套键帽包邮的价格！
    
                     3大必抢理由
                    全新未拆封：原包装没动过，
                    当天发货：拍下就发，物流速度快
                    售后贼靠谱：质保1年免费换新，质量问题我包运费
    
                     功能 实测效果 适合场景
                     工艺 热升华印刷，色彩鲜亮持久，不掉色 日常打字、游戏、收藏
                     材质 PBT材质，不打油、耐磨，手感细腻 高强度使用、汗手玩家
                     透光 字符透光设计，RGB灯效下清晰可见 暗光环境、电竞氛围
                     适配 支持61/68/75/84/87/89/96/98/100/104/108等型号 多键盘通用、DIY玩家
    
                     外观超吸睛！灰原哀主题二次元风
                    - 紫色主色调，搭配灰原哀形象及花朵、猫等元素
                    - 部分键帽阶梯式布局，视觉层次感强
                    - 侧刻设计，正面简洁，侧面透光，低调又个性
    
                     其他细节
                    {sku_info_text}
                    键位：小全套（适配主流配列）
                    颜色：以紫色为主，二次元风格
                    配件：键帽全套 × 1 + 包装盒
    
                     售后保障
                    7天无理由退货（非质量问题运费自理）
                    1年质保免费换新（质量问题我包来回运费）
    
                    标价即卖！全新包邮！！
                    #灰原哀键帽 #PBT热升华 #透光键帽 #二次元键帽 #机械键盘键帽
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
                ],
                temperature=0.1
            )

            cleaned_text_01 = re.sub(r'^[^\S\n]+', '', response.choices[0].message.content.strip(), flags=re.MULTILINE)

            cleaned_text = cleaned_text_01.replace('*', '').replace('#', '')

            return cleaned_text
        except Exception as e:
            logger.error(f"❌ 闲鱼文案生成失败: {e}")
            return ""


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
    """从数据库获取待收藏的商品 URL"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        # 仅查询最新一批且未收藏的商品
        sql = """
        SELECT id, detail_url FROM selected_products
        WHERE detail_url IS NOT NULL
        AND is_collected = 0
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"❌ 读取数据库失败: {e}")
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
    存储或更新 SKU 数据
    用 upsert 保证：不存在则插入，存在则更新
    """
    collection = get_collection()

    doc = {
        "_id": goods_id,
        "goods_id": goods_id,
        "sku": total_result,
        "updated_at": datetime.now(timezone.utc)
    }

    # upsert: 存在则更新，不存在则插入
    result = collection.update_one(
        {"_id": goods_id},
        {"$set": doc},
        upsert=True
    )

    if result.upserted_id:
        logger.info(f"✅ 新增商品 SKU 数据，goods_id: {goods_id}")
    else:
        logger.info(f"🔄 更新商品 SKU 数据，goods_id: {goods_id}")

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
    将 SKU 字典格式化为可读文本

    输入: {'型号': ['苹果11', '苹果12'], '款式': ['防窥款', '高清款']}
    输出: 型号：苹果11、苹果12
          款式：防窥款、高清款
    """
    lines = []
    for category, options in total_sku.items():
        # 每个分类一行，选项用顿号分隔
        line = f"{category}：{'、'.join(options)}"
        lines.append(line)

    return '\n'.join(lines)


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


def start_shelving_process(products):
    """执行遍历收藏流程"""
    if not products:
        logger.info("📭 没有需要处理的商品。")
        return

    # 启动拼多多
    logger.info("🚀 启动拼多多...")
    device.app_stop("com.xunmeng.pinduoduo")
    device.app_start("com.xunmeng.pinduoduo")
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
            device.set_input_ime(True)
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
            device.swipe(540, 1800, 540, 400, steps=3)
            device.swipe(540, 1800, 540, 400, steps=10)
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

            pre_result = None
            while True:
                data = get_hierarchy_safe(ip_port, headers)

                # 滚动加载出未收集的sku信息
                device.swipe(540, 1600, 540, 1150, steps=100)
                time.sleep(1)

                result = extract_sku(data)
                if result == pre_result:
                    break
                smart_merge_skus(final_skus, result)
                pre_result = result

            # sku信息审查和清洗
            # 条件 1：规格类别（Key）超过 2 个
            need_ai_rewrite = len(final_skus) > 2

            # 条件 2：遍历每个规格分类下的具体值，检查是否字数超过 10
            if not need_ai_rewrite:
                for category, values in final_skus.items():
                    for val in values:
                        if len(str(val)) > 10:
                            need_ai_rewrite = True
                            break
                    if need_ai_rewrite: break

            data_to_save = final_skus
            sku_text = format_sku_to_text(data_to_save)

            # 执行逻辑
            if need_ai_rewrite:
                logger.info(f"🚩 检测到规格过于复杂或字数超限，启动 AI 重写模式...")
                # 将字典转为文本描述传给 AI
                refined_skus = ai_tool.process_with_ai(sku_text)
                skus_dict = ai_tool.parse_refined_skus(refined_skus)
                data_to_save = ai_tool.validate_and_clean_skus_dict(skus_dict)
                save_sku_to_mongo(goods_id, data_to_save)
            else:
                data_to_save = ai_tool.validate_and_clean_skus_dict(final_skus)
                save_sku_to_mongo(goods_id, data_to_save)

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
    logger.info("=" * 60)
    logger.info("🚀 爬虫程序启动")
    logger.info("=" * 60)

    # 配置您的手机 IP 端口
    ip_port = "192.168.11.99:38393"

    # 1. 连接设备
    logger.info(f"📱 正在连接设备: {ip_port}")
    device = u2.connect(ip_port)
    logger.info(f"✅ 设备连接成功")

    # 2. 获取待处理数据列表
    logger.info("📦 正在从数据库获取待处理商品列表...")
    pending_list = get_pending_products()
    logger.info(f"📋 待处理商品数量: {len(pending_list)}")

    # 获取指定商品的数据
    # pending_list = [
    #     ("88", "https://mobile.pinduoduo.com/goods.html?goods_id=853041121657"),
    # ]

    # 3. 执行流程
    start_shelving_process(pending_list)

    logger.info("=" * 60)
    logger.info("✨ 所有选品收藏流程执行完毕！")
    logger.info("=" * 60)