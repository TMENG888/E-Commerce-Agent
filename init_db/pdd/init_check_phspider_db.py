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
        create_check_data_sql = """
        CREATE TABLE IF NOT EXISTS `goods_check_data` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            `goods_id` VARCHAR(50) NOT NULL UNIQUE COMMENT '商品ID',
            # --- 数据字段入库校验 ---
            `check_title` TINYINT DEFAULT 0 COMMENT '标题入库校验',
            `check_sku_info` TINYINT DEFAULT 0 COMMENT 'SKU文本入库校验',
            `check_image_info` TINYINT DEFAULT 0 COMMENT '图片描述入库校验',
            `check_sale_copy` TINYINT DEFAULT 0 COMMENT '销售文案入库校验',
            # --- 外部依赖校验 ---
            `check_local_img` TINYINT DEFAULT 0 COMMENT '本地图片文件校验',
            `check_sku_mongo` TINYINT DEFAULT 0 COMMENT 'MongoDB原始数据校验',
            # --- 流程标志 ---
            `check_all_data` TINYINT DEFAULT 0 COMMENT '全流程成功标志(所有项均为1则为1)',
            `check_shelf` TINYINT DEFAULT 0 COMMENT '上架状态',
            `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_check_data_sql)

        print("✅ goods_check_data 表初始化/更新完成！")

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    init_check_table()