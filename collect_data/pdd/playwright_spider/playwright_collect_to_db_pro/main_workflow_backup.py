import asyncio
import os
import random
import glob
import time

import pymysql
from anti_detect import human_delay

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
    def parse_indexes(input_str):
        indexes = set()
        parts = input_str.replace('，', ',').split(',')  # 兼容中英文逗号
        for part in parts:
            if '-' in part:
                start, end = map(int, part.split('-'))
                indexes.update(range(start, end + 1))
            else:
                indexes.add(int(part))
        return sorted(list(indexes))

    # 1. 基础交互
    print("\n请选择起始步骤：")
    print("Step 1. 从头开始")
    print("Step 2. 从评论下载开始")
    print("Step 3. 从文本/参数采集开始")
    print("Step 4. 从AI特征提取/SKU同步开始")
    print("Step 5. 仅生成最终文案")
    start_step = int(input("请输入起始步骤编号: ") or 1)

    # 预定义 goods_id 和 target_url (如果从中间开始，需要先获取它们)
    goods_id = ""
    target_url = ""

    index_list = []
    if start_step == 1:
        raw_input = input("请输入待采集的商品序列 \n（支持 start_index-final_index 或 index1,index2,...）: ")
        index_list = parse_indexes(raw_input)

    else:
        index_list = [0]

    for current_index in index_list:
        print(f"\n{'=' * 20} 正在处理序列号: {current_index} {'=' * 20}")
        # --- 步骤 1: 下载商品详情图 ---
        if start_step == 1:
            print(f"\n--- [Step 1/5] 正在下载商品详情图 (索引: {current_index}) ---")
            downloader = PddGoodsDetailDownloader(BASE_SAVE_DIR)
            goods_id, target_url = await downloader.run(current_index)
        elif start_step in [2, 3]:
            # 如果跳过第一步，必须手动输入 goods_id 以便后续文件定位
            goods_id = input("请输入已采集的商品 goods_id: ")
            target_url = input("请输入该商品的拼多多详情 URL: ")
        else:
            goods_id = input("请输入已采集的商品 goods_id: ")
        
        # 路径准备（无论从哪一步开始，路径定义都是必须的）
        save_path = os.path.join(BASE_SAVE_DIR, goods_id)
        specification_path = os.path.join(SPECIFICATION_DIR, goods_id)
        review_path = os.path.join(REVIEW_SAVE_DIR, goods_id)

        save_root = os.path.join(SHELF_SAVE_DIR, goods_id)
        if not os.path.exists(save_root):
            os.makedirs(save_root)
            print(f"📁 目录已根据 goods_id 准备: {save_root}")

        # [关键修改] Step 1 -> 2 之间增加延迟，模拟人类在看完详情后休息一下再看评论
        if start_step <= 2 and target_url != "0":
            await human_delay(30, 60)  # Step间等待30-60秒

        # --- 步骤 2: 下载评论实拍图 ---
        if start_step <= 2 and target_url != "0":
            print("\n--- [Step 2/5] 正在下载评论实拍图 ---")
            review_downloader = PddReviewDownloader(REVIEW_SAVE_DIR, target_url)
            await review_downloader.run(target_url)
        
        # [关键修改] Step 2 -> 3 之间增加延迟
        if start_step <= 3 and target_url != "0":
            await human_delay(20, 45)

        # --- 步骤 3: 采集文本及参数 ---
        if start_step <= 3 and target_url != "0":
            print("\n--- [Step 3/5] 正在采集标题与规格参数 ---")
            collector = PddFullTextCollector()
            await collector.run(target_url)

        # Step 4-5 不涉及拼多多页面交互，不需要额外的人类行为延迟
        # --- 步骤 4: 并行处理视觉特征提取与 SKU 规格同步 ---
        if start_step <= 4:
            print("\n--- [Step 4/5] 正在并行处理：视觉特征提取 & SKU 规格同步 ---")
            # 初始化处理器
            describer = ProductDescriber(API_KEY)
            sku_processor = SkuProcessor()

            # 此处保留你原有的 asyncio.gather 逻辑...
            async def task_visual_extract():
                image_files = glob.glob(os.path.join(save_path, "*.jpg"))
                image_files += glob.glob(os.path.join(specification_path, "*.jpg"))
                if image_files:
                    max_retries = 3
                    # 注意：如果 describe_product 是同步方法，建议在 run_in_executor 中运行
                    # 这里假设它已被适配为异步或直接运行
                    for attempt in range(max_retries):
                        print(f"正在尝试第{attempt + 1}次商品图信息识别...")
                        v_desc = describer.describe_product(image_files)
                        if '访问量过大' in v_desc:
                            time.sleep(60)
                            continue
                        describer.save_to_db(goods_id, v_desc)
                        print("✅ [并行] 视觉特征提取完成")
                        return v_desc
                    return "识别失败"
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
            await asyncio.gather(task_visual_extract(), task_sku_extract())
        # --- 步骤 5: 生成闲鱼爆款文案 ---
        if start_step <= 5:
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
                            if "速率限制" in final_copy or "网络错误" in final_copy:
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

            wait_time = random.uniform(300, 420)
            print(f"\n休憩片刻... 预计等待 {wait_time:.1f} 秒后开始处理商品 ☕")
            await asyncio.sleep(wait_time)

            print(f"\n✅ 所有任务完成！实拍图已就绪，请在 {review_path} 查看。")



if __name__ == "__main__":
    asyncio.run(main())