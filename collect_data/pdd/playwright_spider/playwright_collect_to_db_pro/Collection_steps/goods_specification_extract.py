import time

import pymysql
import json
from pymongo import MongoClient
from zai import ZhipuAiClient

# --- 配置信息 ---
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

API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
client_zp = ZhipuAiClient(api_key=API_KEY)


class SkuProcessor:
    def __init__(self):
        # 初始化数据库连接
        self.mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        self.mongo_client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])
        self.mongo_db = self.mongo_client[MONGO_CONFIG["db"]]
        self.mongo_col = self.mongo_db[MONGO_CONFIG["collection"]]

    def fetch_mysql_data(self, target_goods_ids=None):
        """
        从 MySQL 获取数据
        :param target_goods_ids: list, 指定要处理的 goods_id 列表。如果为 None 则处理全部。
        """
        try:
            with self.mysql_conn.cursor(pymysql.cursors.DictCursor) as cursor:
                if target_goods_ids and len(target_goods_ids) > 0:
                    # 构造 IN 查询，例如: WHERE goods_id IN ('id1', 'id2')
                    format_strings = ','.join(['%s'] * len(target_goods_ids))
                    sql = f"SELECT goods_id, text_desc FROM goods_descriptions WHERE goods_id IN ({format_strings})"
                    cursor.execute(sql, tuple(target_goods_ids))
                else:
                    # 默认处理全部
                    sql = "SELECT goods_id, text_desc FROM goods_descriptions"
                    cursor.execute(sql)

                return cursor.fetchall()
        except Exception as e:
            print(f"❌ MySQL 读取失败: {e}")
            return []

    def process_with_ai(self, goods_id, text_desc):
        """调用大模型解析 SKU 并改写规格"""
        max_retries = 3

        # Messages
        messages = [
            {
                "role": "system",
                "content": f"""
                你是一个专业的电商数据格式化助手。你的任务是根据提供的商品信息，提取并格式化SKU数据。请严格遵守以下规则：1. 从SKU价格详情中提取所有SKU组合，每个SKU输出为一个独立的字典。2. 将SKU属性归纳为最多两个规格类型（如'颜色'和'容量'），如果原始SKU属性超过两个，你需要根据语义合并为两个。3. 每个规格值（如'极速白'、'10000毫安'）的字数必须严格控制在5个汉字以内，但要尽可能包含丰富信息，使其接近10字上限，控制5字以内，否则要求重新生成4. 输出必须是一个字典列表，每个字典包含固定的键：'goods_id'、两个规格类型名（如'颜色'、'容量'）、'price'和'original_sku'。5. 'goods_id'的值使用提供的变量。6. 'price'的值是浮点数。7. 'original_sku'的值是原始SKU文本的完整复制。
        
                输出格式要求:
                JSON (一个Python字典列表，可直接被Python的json.loads解析)
                一定要有goods_id，price，original_sku这些键值对
                """
            },
            {
                "role": "assistant",
                "content": f"[{{'goods_id': '{goods_id}', '颜色': '极速白', '容量': '10000毫安', 'price': 21.58, 'original_sku': '极速白 + 10000毫安 (￥21.58)'}}, {{'goods_id': '{goods_id}', '颜色': '极速白', '容量': '20000毫安', 'price': 23.79, 'original_sku': '极速白 + 20000毫安 (￥23.79)'}}, {{'goods_id': '{goods_id}', '颜色': '极速黑', '容量': '3000毫安', 'price': 13.79, 'original_sku': '极速黑 + 3000毫安 (￥13.79)'}}, {{'goods_id': '{goods_id}', '颜色': '极速黑', '容量': '10000毫安', 'price': 21.58, 'original_sku': '极速黑 + 10000毫安 (￥21.58)'}},{{'goods_id': '{{goods_id}}', '颜色': '极速黑', '容量': '20000毫安', 'price': 23.79, 'original_sku': '极速黑 + 20000毫安 (￥23.79)'}}]"
            },
            {
                "role": "user",
                "content": f"""
                请根据以下信息，生成SKU列表。
                SKU价格及详情：{text_desc}
                商品ID：{goods_id}
        
                请按照要求，输出所有SKU的JSON列表。
                """
            }
        ]
        for attempt in range(max_retries):
            try:

                print(f"正在尝试第{attempt + 1}次SKU信息结构化转存...")

                response = client_zp.chat.completions.create(
                    model="GLM-4-Flash-250414",
                    messages=messages,
                    temperature=0.1,
                    thinking={"type": "disabled"}
                )
                content = response.choices[0].message.content
                clean_content = content.replace("```json", "").replace("```python", "").replace("```", "").strip()

                return json.loads(clean_content)
            except Exception as e:
                error_msg = str(e)
                if '速率限制' in error_msg:
                    time.sleep(30)
                    continue
                print(f"❌ AI 解析失败 (ID: {goods_id}): {e}")
                return None
        return None

    def validate_and_clean_skus(self, data_list):
        """
        校验规格数据：如果某个规格类型下只有一种具体规格值，则剔除该规格维度。
        """
        if not data_list:
            return []

        # 1. 识别所有的规格键名 (排除内置字段)
        exclude_keys = {"goods_id", "price", "original_sku", "_id"}
        all_keys = set()
        for item in data_list:
            all_keys.update(item.keys())
        spec_keys = [k for k in all_keys if k not in exclude_keys]

        # 2. 统计每个规格键下的唯一值数量
        keys_to_remove = []
        for key in spec_keys:
            unique_values = set()
            for item in data_list:
                if key in item:
                    unique_values.add(item[key])

            # 如果该规格类型下只有一种值，标记为需要删除
            if len(unique_values) <= 1:
                keys_to_remove.append(key)
                print(f"🧹 规格校验：维度 '{key}' 下仅有单一值 {list(unique_values)}，已执行字段剔除。")

        # 3. 执行删除操作
        if keys_to_remove:
            for item in data_list:
                for key in keys_to_remove:
                    if key in item:
                        del item[key]

        return data_list

    def save_to_mongodb(self, data_list):
        """存入 MongoDB：先清理旧 goods_id 数据，再插入新规格"""
        if not data_list:
            return

        try:
            # 1. 获取当前批次的 goods_id（假设一批数据属于同一个商品）
            # 如果 data_list 跨多个商品，可以使用 set 收集
            target_goods_ids = list(set(item["goods_id"] for item in data_list))

            # 2. 检查并删除旧数据
            for gid in target_goods_ids:
                # 统计是否存在旧数据
                count = self.mongo_col.count_documents({"goods_id": gid})
                if count > 0:
                    self.mongo_col.delete_many({"goods_id": gid})
                    print(f"🧹 已清理商品 {gid} 的 {count} 条旧规格数据")

            # 3. 批量插入新数据
            # 由于已经删除了旧数据，直接使用 insert_many 效率更高
            # 如果你担心逻辑中断，也可以继续使用 update_one 的 upsert 模式
            self.mongo_col.insert_many(data_list)

            print(f"✅ 成功同步 {len(data_list)} 条新规格到 MongoDB")

        except Exception as e:
            print(f"❌ MongoDB 处理失败: {e}")

    def run(self, specific_ids=None):
        """
        运行程序
        :param specific_ids: list, 传入需要处理的 goods_id 列表，如 ["814315162746"]
        """
        print(f"🚀 开始处理 SKU 数据同步... {'(指定 ID 模式)' if specific_ids else '(全量模式)'}")
        rows = self.fetch_mysql_data(specific_ids)

        if not rows:
            print("⚠️ 未找到匹配的商品数据。")
            return

        for row in rows:
            gid = row['goods_id']
            desc = row['text_desc']
            if not desc:
                print(f"⏩ 商品 {gid} 的 text_desc 为空，跳过。")
                continue

            print(f"🔍 正在处理商品: {gid}")
            structured_skus = self.process_with_ai(gid, desc)

            if structured_skus:
                cleaned_skus = self.validate_and_clean_skus(structured_skus)
                self.save_to_mongodb(cleaned_skus)

        print("🏁 全部数据处理完成")


if __name__ == "__main__":
    processor = SkuProcessor()

    # --- 在此处指定需要处理的 goods_id ---
    # 如果想处理全部商品，设为 None 即可
    target_ids = ["644782391276"]

    processor.run(specific_ids=target_ids)