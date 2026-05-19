import pymysql

# 数据库连接配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}


def init_check_table():
    """初始化商品采集校验表（已增加上架图校验字段）"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        # 创建校验状态表
        print(f"🛠️ 正在初始化/更新校验表: goods_check_results...")

        # 使用 ALTER TABLE 逻辑确保如果表已存在也能增加新字段
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS goods_check_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            goods_id VARCHAR(50) NOT NULL UNIQUE COMMENT '商品ID',
            check_main_img TINYINT DEFAULT 0 COMMENT '详情图校验',
            check_review_img TINYINT DEFAULT 0 COMMENT '实拍图校验',
            check_spec_img TINYINT DEFAULT 0 COMMENT '规格图校验',
            check_shelf_img TINYINT DEFAULT 0 COMMENT '上架预备图校验: 1-已生成, 0-未生成',
            check_sku_mongo TINYINT DEFAULT 0 COMMENT 'MongoDB SKU数据校验',
            check_ai_copy TINYINT DEFAULT 0 COMMENT 'AI文案校验',
            check_all TINYINT DEFAULT 0 COMMENT '全流程成功标志',
            check_shelf TINYINT DEFAULT 0 COMMENT '上架状态: 1-已上架, 0-未上架',
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_sql)

        # 检查并补齐字段（防止表已存在但没新字段的情况）
        try:
            cursor.execute(
                "ALTER TABLE goods_check_results ADD COLUMN check_shelf_img TINYINT DEFAULT 0 AFTER check_spec_img")
            print("✅ 已成功添加 check_shelf_img 字段。")
        except:
            pass  # 字段已存在则跳过

        print("✅ goods_check_results 表初始化/更新完成！")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    init_check_table()