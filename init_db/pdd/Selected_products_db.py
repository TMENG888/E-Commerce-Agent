import pymysql

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

def init_best_products_table():
    """初始化选品结果存储表"""
    try:
        conn = pymysql.connect(
            host=MYSQL_CONFIG['host'],
            user=MYSQL_CONFIG['user'],
            password=MYSQL_CONFIG['password']
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']} CHARACTER SET utf8mb4")
        cursor.execute(f"USE {MYSQL_CONFIG['database']}")

        # 创建选品推荐表
        # 新增 detail_url 和 is_collected 字段
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS selected_products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            original_index INT COMMENT '大模型输出的原始索引',
            product_name VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) COMMENT '商品价格',
            decision_reason TEXT COMMENT 'AI分析的决策理由与销售策略',
            detail_url VARCHAR(500) DEFAULT NULL COMMENT '商品详情页链接',
            is_collected TINYINT(1) DEFAULT 0 COMMENT '是否已收藏: 0-未收藏, 1-已收藏',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_sql)
        print("✅ selected_products 表初始化成功！")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    init_best_products_table()