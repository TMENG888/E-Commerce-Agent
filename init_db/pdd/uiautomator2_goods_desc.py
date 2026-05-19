import pymysql
from pymysql.cursors import DictCursor

# 数据库配置
MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "db": "pdd_db",
    "charset": "utf8mb4"
}


def create_goods_descriptions_table():
    """创建 goods_descriptions 表"""

    connection = pymysql.connect(**MYSQL_CONFIG, cursorclass=DictCursor)

    create_sql = """
    CREATE TABLE IF NOT EXISTS `goods_desc` (
        `id` INT NOT NULL AUTO_INCREMENT,
        `goods_id` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
        `title` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '商品标题',
        `sku_info` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT 'SKU规格数据',
        `image_info` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '商品图片信息',
        `sale_copy` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '闲鱼销售文案',
        `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (`id`) USING BTREE,
        UNIQUE INDEX `goods_id`(`goods_id` ASC) USING BTREE
    ) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(create_sql)
            connection.commit()
            print("✅ 表 goods_descriptions 创建成功")
    except Exception as e:
        print(f"❌ 建表失败: {e}")
    finally:
        connection.close()


if __name__ == "__main__":
    create_goods_descriptions_table()