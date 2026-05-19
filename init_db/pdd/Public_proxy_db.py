import pymysql

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

def create_proxy_pool_table():
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        create_sql = """
        CREATE TABLE IF NOT EXISTS proxy_pool (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
            ip_port VARCHAR(50) NOT NULL COMMENT 'IP地址及端口',
            response_time VARCHAR(50) COMMENT '响应时间',
            verify_time VARCHAR(50) COMMENT '最后验证时间',
            collect_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '采集入库时间',
            UNIQUE KEY uk_ip_port (ip_port)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IP代理池表';
        """
        cursor.execute(create_sql)
        print("✅ 代理池表 proxy_pool 创建成功！")

    except Exception as e:
        print(f"❌ 创建失败：{e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    create_proxy_pool_table()