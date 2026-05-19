import pymysql
from zai import ZhipuAiClient
from openai import OpenAI

# 1. 数据库配置 (沿用你的 goods_db.py 配置)
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4',
    'autocommit': True
}

# 2. 智谱AI 配置
ZHIPU_API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
client_zp = ZhipuAiClient(api_key=ZHIPU_API_KEY)

DeepSeek_API_Key = "sk-44c4fde8a913435caba4cb6f1c123fb4"
client_ds = OpenAI(api_key=DeepSeek_API_Key , base_url="https://api.deepseek.com")

import json


def format_xianyu_copy(data_input):
    # 如果 data_input 是字符串则转为字典，如果是字典则直接使用
    data = json.loads(data_input) if isinstance(data_input, str) else data_input

    # 1. 拼接 product_name 和 condition_description
    section1 = f"{data['product_name']}，{data['condition_description']}"

    # 2. 拼接 usage_experience 和 target_scenarios
    section2 = f"{data['usage_experience']}\n{data['target_scenarios']}"

    # 3. 处理 package_contents
    section3 = f"{data['package_contents']}"

    # 4. 处理 available_options (考虑到它是字典，需转为字符串)
    options = data['available_options']
    options_str = "\n".join([f"{k}：{v}" for k, v in options.items()])
    section4 = f"{options_str}"

    # 5. 处理 transaction_terms
    section5 = f"{data['transaction_terms']}"

    # 最终合并，使用 \n\n 实现空白行分隔
    return f"{section1}\n\n{section2}\n\n{section3}\n\n{section4}\n\n{section5}"


def generate_xianyu_copy(text_desc, image_desc):
    """
    根据商品原始描述和图片识别描述，生成闲鱼爆款文案
    """
    # 动态任务指令：将逻辑、数据、要求缝合
    prompt = f"""
    ### Role
    你是一个闲鱼电商运营专家，擅长将冰冷的商品参数转化为极具诱惑力的销售文案。
    
    ### Task
    根据提供的商品基础信息 {text_desc} 和视觉特征 {image_desc}，填充以下 JSON 字典。
    
    ### Data Schema & Requirements
    1. product_name: 精准定位到品牌、型号和关键词，这是搜索权重的核心。
    2. condition_description: 强调“全新/未拆封”成色细节，成色描述不能冲突，比如全新未拆封不能和99新成色同时出现。
    3. usage_experience: 将产品的功能转化为感性认知，吸引感性消费者。
    4. target_scenarios: 通过具体场景代入感来创造购买需求（哪怕买家原本没打算买）。
    5. package_contents: 详列清单，强调“开箱即用”。
    6. available_options: 对应“颜色、款式可选...”，清晰列出SKU（不加入价格）如：颜色可选：蓝色、白色，款式可选：小号、中号，
    但是款式要和产品信息有所区别，比如蓝色，我就改为天蓝色，进阶版就改为豪华款，要和厂家给的产品sku规格意思一致，表达不同，又要方便买家精准选购。
    7. transaction_terms: 对应“可私聊...包邮”，明确售后和物流责任，加速成交决策，不要提及具体的快递品牌，如顺丰、京东等等。
    
    ### Constraint
    仅输出 JSON 格式结果，禁止包含 Markdown 格式符 ```json，确保输出内容可直接被 python json.loads() 解析。
    
    {{
        "product_name": "",
        "condition_description": "",
        "usage_experience": "",
        "target_scenarios": "",
        "package_contents": "",
        "available_options": {{"规格1可选":"蓝色、白色、黑色","规格2可选":"小号、中号、大号"}},
        "transaction_terms": ""
    }}
    """

    try:
        response = client_zp.chat.completions.create(
            model="glm-4.7-flash",
            messages=[
                {"role": "user", "content": prompt}
            ],
            thinking={"type": "enabled"},
            max_tokens=131072,
            temperature=0.1
        )

        # response = client_ds.chat.completions.create(
        #     model="deepseek-chat",
        #     messages=[
        #         {"role": "user", "content": prompt}
        #     ]
        # )

        return format_xianyu_copy(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ AI 生成失败: {e}")
        return str(e)

def process_goods_descriptions():
    """
    主逻辑：读取、生成、更新
    """
    try:
        # 连接数据库
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. 查询所有 sales_desc 为空的数据
        query_sql = "SELECT id, text_desc, image_desc FROM goods_descriptions WHERE sales_desc IS NULL OR sales_desc = ''"
        cursor.execute(query_sql)
        rows = cursor.fetchall()

        if not rows:
            print("✨ 没有需要处理的数据。")
            return

        print(f"🚀 开始处理 {len(rows)} 条商品数据...")

        for row in rows:
            record_id = row['id']
            t_desc = row['text_desc']
            i_desc = row['image_desc']

            print(f"📦 正在处理 ID: {record_id}...")

            # 2. 调用 AI 生成文案
            ai_copy = generate_xianyu_copy(t_desc, i_desc)

            if ai_copy:
                # 3. 更新回数据库
                update_sql = "UPDATE goods_descriptions SET sales_desc = %s WHERE id = %s"
                cursor.execute(update_sql, (ai_copy, record_id))
                print(f"✅ ID: {record_id} 文案生成并存入数据库")
            else:
                print(f"⚠️ ID: {record_id} 跳过处理")

    except Exception as e:
        print(f"❌ 程序运行出错: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 数据库连接已关闭")

if __name__ == "__main__":
    process_goods_descriptions()