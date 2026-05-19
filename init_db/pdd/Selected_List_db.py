import pymysql

# 数据库连接配置（保持不变）
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

def init_rank_goods_table():
    """初始化拼多多电脑榜单商品表（精简字段版）"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()

        print("🛠️ 正在创建精简版榜单表：pdd_rank_goods")

        # 只保留：id、rank_num、goods_message、price、create_time
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS pdd_rank_goods (
        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
        rank_num INT COMMENT '榜单排名',
        goods_message VARCHAR(1000) COMMENT '商品信息',
        price VARCHAR(50) COMMENT '商品价格',
        -- 新增：专门存储日期的字段（格式：2026-04-23）
        collect_date DATE NOT NULL COMMENT '采集日期',
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
        -- 修改：删除旧的 uk_rank_num，改为日期和排名的联合唯一索引
        UNIQUE KEY uk_date_rank (collect_date, rank_num)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='拼多多电脑榜单商品表';
        """
        cursor.execute(create_table_sql)
        print("✅ 精简版榜单表创建完成！")

    except Exception as e:
        print(f"❌ 创建表失败：{e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    init_rank_goods_table()