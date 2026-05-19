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


def init_database():
    """执行数据库创建和表结构初始化"""
    try:
        # 1. 连接 MySQL 服务器（不指定数据库，用于创建数据库）
        conn = pymysql.connect(
            host=MYSQL_CONFIG['host'],
            user=MYSQL_CONFIG['user'],
            password=MYSQL_CONFIG['password']
        )
        cursor = conn.cursor()

        # 2. 创建数据库
        print(f"🛠️ 正在检查数据库: {MYSQL_CONFIG['database']}...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']} CHARACTER SET utf8mb4")
        cursor.execute(f"USE {MYSQL_CONFIG['database']}")

        # 3. 创建商品描述表
        print("🛠️ 正在初始化表结构: goods_descriptions...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS goods_descriptions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            goods_id VARCHAR(50) UNIQUE,
            text_desc TEXT COMMENT '商品标题/文本描述',
            image_desc TEXT COMMENT '视觉模型提取描述',
            sales_desc TEXT COMMENT '闲鱼销售文案',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_sql)

        print("✅ 数据库与表结构初始化成功！")

    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    init_database()