import os
import glob
import pymysql
from pymongo import MongoClient

# --- 配置 ---
MYSQL_CONFIG = {
    'host': 'localhost', 'user': 'root', 'password': '123456',
    'database': 'pdd_db', 'charset': 'utf8mb4', 'autocommit': True
}
MONGO_CONFIG = {
    "host": "localhost", "port": 27017,
    "db": "Goofish", "collection": "Goods_Specification"
}

# 路径配置
BASE_SAVE_DIR = r"C:\Users\31193\Pictures\商品图"
REVIEW_SAVE_DIR = r"C:\Users\31193\Pictures\商品实拍图"
SPECIFICATION_DIR = r"C:\Users\31193\Pictures\商品规格图"
SHELF_SAVE_DIR = r"C:\Users\31193\Pictures\商品上架图"


def get_all_goods_ids(date):
    """从描述表中获取所有需要校验的商品 ID"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 修改SQL查询，只匹配日期部分（年-月-日）
            sql = "SELECT DISTINCT goods_id FROM goods_descriptions WHERE DATE(created_at) = %s"
            # 将输入的月日格式转换为完整日期格式（2026-月-日）
            full_date = f"2026-{date}"
            cursor.execute(sql, (full_date,))
            return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_pending_shelf_list():
    """输出校验通过且未上架的商品 ID 列表"""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 筛选条件：all_ok=1 且 check_shelf=0
            # 注意：check_shelf 字段通常在 goods_check_results 或 goods_info 表中，请根据实际表名修改
            sql = """
            SELECT goods_id FROM goods_check_results 
            WHERE check_all = 1 AND check_shelf = 0
            """
            cursor.execute(sql)
            results = [row[0] for row in cursor.fetchall()]

            print("\n" + "-" * 50)
            print(f"待自动化上架商品清单:")
            if results:
                for i, gid in enumerate(results, 1):
                    print(f"[{i}] 商品ID: {gid}")
            else:
                print("📭 暂无满足上架条件的商品。")
            print("-" * 50 + "\n")
            return results
    finally:
        conn.close()


class DataValidator:
    def __init__(self, goods_id):
        self.num = 0
        self.goods_id = goods_id
        self.mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        self.mongo_client = MongoClient(MONGO_CONFIG["host"], MONGO_CONFIG["port"])

    def check_files(self, folder_path, label_name):
        """检查物理文件夹下是否有有效图片（>5KB）"""
        target_path = os.path.join(folder_path, self.goods_id)
        if not os.path.exists(target_path):
            return 0

        valid_files = [f for f in glob.glob(os.path.join(target_path, "*.*"))
                       if os.path.getsize(f) > 5120]

        status = 1 if len(valid_files) > 0 else 0
        return status

    def check_db_field(self, field_name):
        """检查数据库字段有效性"""
        with self.mysql_conn.cursor() as cursor:
            sql = f"SELECT {field_name} FROM goods_descriptions WHERE goods_id=%s"
            cursor.execute(sql, (self.goods_id,))
            res = cursor.fetchone()
            invalid_keywords = ["识别异常", "访问量过大", "网络错误", "None", ""]
            if res and res[0] and str(res[0]).strip() not in invalid_keywords:
                return 1
            return 0

    def check_mongo_data(self):
        """检查 MongoDB 规格数据"""
        db = self.mongo_client[MONGO_CONFIG["db"]]
        col = db[MONGO_CONFIG["collection"]]
        return 1 if col.count_documents({"goods_id": self.goods_id}) > 0 else 0

    def validate_and_save(self):
        """执行全流程校验并打印详细结果"""
        # 1. 采集各项结果
        results = {
            "详情图校验 (Main)": self.check_files(BASE_SAVE_DIR, "详情图"),
            "实拍图校验 (Review)": self.check_files(REVIEW_SAVE_DIR, "实拍图"),
            "规格图校验 (Spec)": self.check_files(SPECIFICATION_DIR, "规格图"),
            "上架图校验 (Shelf)": self.check_files(SHELF_SAVE_DIR, "上架图"),
            "SKU数据 (Mongo)": self.check_mongo_data(),
            "AI爆款文案 (MySQL)": self.check_db_field("sales_desc")
        }

        shelf_check = results["上架图校验 (Shelf)"]
        other_checks = {k: v for k, v in results.items() if k != "上架图校验 (Shelf)"}
        all_checks = [k for k, v in results.items() if v == 0]

        # 2. 计算 check_all (必须全部为1)
        other_missing_items = [k for k, v in other_checks.items() if v == 0]
        other_ok = 1 if not other_missing_items else 0
        all_ok = 1 if not all_checks else 0

        if other_ok == 1 and shelf_check == 0:
            print(f"商品ID: {self.goods_id}")
            self.num += 1

        # 3. 更新数据库
        try:
            with self.mysql_conn.cursor() as cursor:
                sql = """
                INSERT INTO goods_check_results 
                (goods_id, check_main_img, check_review_img, check_spec_img, 
                 check_shelf_img, check_sku_mongo, check_ai_copy, check_all)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    check_main_img=VALUES(check_main_img),
                    check_review_img=VALUES(check_review_img),
                    check_spec_img=VALUES(check_spec_img),
                    check_shelf_img=VALUES(check_shelf_img),
                    check_sku_mongo=VALUES(check_sku_mongo),
                    check_ai_copy=VALUES(check_ai_copy),
                    check_all=VALUES(check_all)
                """
                params = (
                    self.goods_id,
                    results["详情图校验 (Main)"],
                    results["实拍图校验 (Review)"],
                    results["规格图校验 (Spec)"],
                    results["上架图校验 (Shelf)"],
                    results["SKU数据 (Mongo)"],
                    results["AI爆款文案 (MySQL)"],
                    all_ok
                )
                cursor.execute(sql, params)
        except Exception as e:
            print(f"❌ 数据库写入异常: {e}")
            return False
        finally:
            self.mysql_conn.close()
            self.mongo_client.close()
        return self.num


if __name__ == "__main__":
    # 测试代码
    count = 0
    gids = get_all_goods_ids("4-22")

    print("-" * 50)
    print(f"待人工完成上架图清单:")
    for gid in gids:
        v = DataValidator(gid)
        count = v.validate_and_save()

    if count == 0:
        print("📭 暂无待处理上架图的商品。")
    get_pending_shelf_list()