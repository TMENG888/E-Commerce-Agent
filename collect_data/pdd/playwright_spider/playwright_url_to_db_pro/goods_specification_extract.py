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

        prompt = f"""
        ### Role
        你是一个电商数据结构化专家。

        ### Task
        解析【SKU价格详情】。将每一组 SKU 拆解并存入 JSON 数组。

        ### 处理要求：
        1. **规格数量**：首先清点下SKU详情当中的具体规格数量，然后对规格类型进行归纳，并给出规格类型描述，规格类型下的具体规格描述的数量
        乘积要等于SKU详情当中的具体规格数量,如总共有4个SKU商品，spec_1下有两个规格，spec_2下有两个规格，那2乘以2为4则处理正确。
        2. **动态键名**：规格类型不要直接使用 spec_1, spec_2 或规格1，规格2。请根据内容自动归纳判断规格类型，而且只允许有两个规格类型。
           - 示例：如果“双边耳机+麦克风【杜比音效】”归纳为规格类型为“款式”，“3.5mm圆孔【手机专用】”归纳为规格类型为“适配机型”。
        3. **规格改写**：
           - 只能有两个规格类型，因此当SKU详情当中存在不止两种规格，需要对多种规格做总结为两种规格类型的描述，而且总结的描述要简洁明了，
           比如“LT820奶白暖光 无线版”转换为“奶白＋暖光”和“无线版”这两个规格类型，不能拆为三个规格类型描述，如“奶白色”“暖光”和“无线版”，
           还有比如“LT820奶白暖光-无线版键鼠套装”转换为“LT820奶白暖光”和“无线版”，不要处理为缺失的规格描述，如“奶白”和“暖光”，少了“无线”。
           - 对具体的规格做改写，如“蔚蓝色”改为“天青蓝”，“暖光”改为“暖色光”，“有线版”改为“有线”。
           - 具体规格描述不能超过20个字，因此如果超出则需要对该规格描述做简洁化处理。
        4. **价格提取**：只保留数字（如“券后65.8”提取为 65.8）。
        5. **字段包含**：每个对象必须包含 "goods_id" 和 "price"。

        ### 待处理数据
        {text_desc}

        ### Output Format (仅输出纯 JSON 数组，不含 Markdown 格式符)
        [
            {{
                "goods_id": "{goods_id}",
                "规格1": "具体规格描述",
                "规格2": "具体规格描述",
                "price": ,
                "original_sku": "完整原始SKU内容"
            }}
        ]
        """
        for attempt in range(max_retries):
            try:

                print(f"正在尝试第{attempt + 1}次SKU信息结构化转存...")

                response = client_zp.chat.completions.create(
                    model="glm-4.7-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    thinking={"type": "disabled"}
                )
                content = response.choices[0].message.content
                clean_content = content.replace("```json", "").replace("```", "").strip()

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