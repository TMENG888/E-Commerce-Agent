import os
import base64
import glob
import pymysql  # 引入 pymysql
from typing import List
from zai import ZhipuAiClient

# --- 配置 ---
API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
MODEL_NAME = "glm-4.6v-flash"

# 数据库配置（引用自 goods_db.py）
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

class ProductDescriber:
    def __init__(self, api_key: str):
        self.client = ZhipuAiClient(api_key=api_key)

    def _encode_image(self, image_path: str):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def describe_product(self, image_paths: List[str]):
        content_list = []
        for path in image_paths:
            img_b64 = self._encode_image(path)
            content_list.append({
                "type": "image_url",
                "image_url": {"url": img_b64}
            })

        content_list.append({
            "type": "text",
            "text": (
                "你是一个电商专家。请分析这些商品图片，提取出详细的商品描述。"
                "要求包含：商品名称、核心卖点、外观设计、功能参数。用简洁的列表格式输出。"
            )
        })

        try:
            max_retries = 3

            for attempt in range(max_retries):
                print(f"正在尝试第{attempt + 1}次商品图信息识别...")

                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": content_list}],
                    thinking={"type": "enabled"}
                )

                result_content = response.choices[0].message.content

                if '访问量过大' in result_content:
                    continue

                return result_content
            return "识别失败"
        except Exception as e:
            return f"识别异常: {str(e)}"

    def save_to_db(self, goods_id, image_desc):
        """将描述信息更新到数据库的 image_desc 字段"""
        try:
            conn = pymysql.connect(**MYSQL_CONFIG)
            with conn.cursor() as cursor:
                # 使用 ON DUPLICATE KEY UPDATE 确保 goods_id 存在时更新 image_desc
                sql = """
                INSERT INTO goods_descriptions (goods_id, image_desc)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE image_desc = VALUES(image_desc)
                """
                cursor.execute(sql, (goods_id, image_desc))
            print(f"✅ 描述信息已成功同步到数据库 image_desc 字段: ID={goods_id}")
        except Exception as e:
            print(f"❌ 数据库存储失败: {e}")
        finally:
            if 'conn' in locals():
                conn.close()