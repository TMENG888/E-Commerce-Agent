import asyncio
import os
import glob
import time

import pymysql

# 导入原有脚本中的类
from goods_images_description import PddGoodsDetailDownloader
from extract_goods_description import ProductDescriber
from goods_text_description import PddFullTextCollector
from goofish_sale_desc import generate_xianyu_copy, MYSQL_CONFIG
from download_images_folder import PddReviewDownloader
from goods_specification_extract import SkuProcessor

# --- 全局基础配置 ---
BASE_SAVE_DIR = r"C:\Users\31193\Pictures\商品图"
REVIEW_SAVE_DIR = r"C:\Users\31193\Pictures\商品实拍图"
SHELF_SAVE_DIR = r"C:\Users\31193\Pictures\商品上架图"
API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
SPECIFICATION_DIR = r"C:\Users\31193\Pictures\商品规格图"

async def main():
    # 1. 用户交互输入
    index = int(input("请输入待采集的商品序列号: "))

    # --- 步骤 1: 下载商品详情图 ---
    print("\n--- [Step 1/5] 正在下载商品详情图 ---")
    downloader = PddGoodsDetailDownloader(BASE_SAVE_DIR)
    goods_id, target_url = await downloader.run(index)

    # 路径准备
    save_path = os.path.join(BASE_SAVE_DIR, goods_id)
    specification_path = os.path.join(SPECIFICATION_DIR, goods_id)
    review_path = os.path.join(REVIEW_SAVE_DIR, goods_id)

    # --- 步骤 2: 下载评论实拍图 (新增) ---
    print("\n--- [Step 2/5] 正在下载评论实拍图 (买家秀) ---")
    review_downloader = PddReviewDownloader(REVIEW_SAVE_DIR, target_url)
    await review_downloader.run(target_url)

    save_root = os.path.join(SHELF_SAVE_DIR, goods_id)
    if not os.path.exists(save_root):
        os.makedirs(save_root)
        print(f"📁 目录已根据 goods_id 准备: {save_root}")

    # --- 步骤 3: 采集文本及参数 ---
    print("\n--- [Step 3/5] 正在采集标题与规格参数 ---")
    collector = PddFullTextCollector()
    await collector.run(target_url)

    # --- 步骤 4: 并行处理视觉特征提取与 SKU 规格同步 ---
    print("\n--- [Step 4/5] 正在并行处理：视觉特征提取 & SKU 规格同步 ---")

    # 初始化处理器
    describer = ProductDescriber(API_KEY)
    sku_processor = SkuProcessor()

    # 定义视觉提取任务
    async def task_visual_extract():
        image_files = glob.glob(os.path.join(save_path, "*.jpg"))
        image_files += glob.glob(os.path.join(specification_path, "*.jpg"))
        if image_files:
            # 注意：如果 describe_product 是同步方法，建议在 run_in_executor 中运行
            # 这里假设它已被适配为异步或直接运行
            v_desc = describer.describe_product(image_files)
            describer.save_to_db(goods_id, v_desc)
            print("✅ [并行] 视觉特征提取完成")
            return v_desc
        else:
            print("⚠️ [并行] 未找到图片，跳过视觉提取")
            return "暂无图片特征"

    # 定义 SKU 规格提取任务
    async def task_sku_extract():
        try:
            # 内部逻辑：从 MySQL 取 -> AI 解析 -> 存 MongoDB
            # 传入 specific_ids 参数，只处理当前这个 goods_id
            sku_processor.run(specific_ids=[goods_id])
            print(f"✅ [并行] 商品 {goods_id} 规格数据已同步至 MongoDB")
        except Exception as e:
            print(f"❌ [并行] SKU 规格同步失败: {e}")

    # 使用 asyncio.gather 并行执行两个任务
    # 这将同时启动视觉识别和规格解析，显著节省总耗时
    visual_desc, _ = await asyncio.gather(
        task_visual_extract(),
        task_sku_extract()
    )

    # --- 步骤 5: 生成闲鱼爆款文案 ---
    print("\n--- [Step 5/5] 正在生成最终闲鱼文案 ---")
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 获取刚刚存入的 text_desc 和 image_desc
            cursor.execute("SELECT text_desc, image_desc FROM goods_descriptions WHERE goods_id = %s", (goods_id,))
            record = cursor.fetchone()

            if record:
                max_retries = 4
                for attempt in range(max_retries):
                    print(f"🚀 正在生成文案，请稍候... (失败后尝试次数: {attempt})")
                    # 传入采集到的文本和图片特征生成文案
                    final_copy = generate_xianyu_copy(record['text_desc'], record['image_desc'])
                    if "速率限制" or "网络错误" in final_copy:
                        print(f"❌ 爆款文案生成失败，正在等待重试... ")
                        time.sleep(300)
                        continue
                    else:
                        cursor.execute(
                            "UPDATE goods_descriptions SET sales_desc = %s WHERE goods_id = %s",
                            (final_copy, goods_id)
                        )
                        print("✨ 爆款文案已生成并存入数据库！")
                        print("\n" + "=" * 30 + " 最终预览 " + "=" * 30)
                        print(final_copy)
                        print("=" * 69)
                        break
                if "速率限制" in final_copy:
                    print("❌ 爆款文案生成失败，请稍后再试")
    except Exception as e:
        print(f"❌ 文案生成环节出错: {e}")
    finally:
        if 'conn' in locals(): conn.close()

    print(f"\n✅ 所有任务完成！实拍图已就绪，请在 {review_path} 查看。")


if __name__ == "__main__":
    asyncio.run(main())