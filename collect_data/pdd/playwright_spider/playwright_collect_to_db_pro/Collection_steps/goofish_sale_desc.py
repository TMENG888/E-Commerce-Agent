import pymysql
import json
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


def clean_llm_response(text):
    """
    清洗大模型返回的文案：
    去掉所有多余空格、多余符号 • * — 等
    """
    import re

    # 1. 去掉所有前置空格、缩进空格
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)

    # 2. 去掉多余符号：• ** — -
    text = re.sub(r'•\s*\*\*|•|\*\*|—|-{2,}', '', text)

    return text


def generate_xianyu_copy(text_desc, image_desc):
    """
    根据商品原始描述和图片识别描述，生成闲鱼爆款文案
    """
    # 动态任务指令：将逻辑、数据、要求缝合
    try:
        response = client_zp.chat.completions.create(
            model="GLM-4-Flash-250414",
            messages=[
        {
            "role": "system",
            "content": f"""
                你是一位专业的电商文案撰写专家，擅长将商品信息转化为极具吸引力和销售力的营销文案。请严格遵循以下要求：
                1. 核心任务：基于用户提供的商品信息，创作一份营销文案。文案风格必须与提供的‘目标案例’高度一致，包括其结构、语气、促销元素和免责声明风格。
                2. 输出规范：
                   - 开头使用【】强调促销主题，但不要出现 ** 加粗标识。
                   - 使用‘•’符号列出核心卖点，每个卖点用简短、有力的句子描述。
                   - 在卖点后，补充关于包装、配件、兼容性、使用建议等关键说明。
                   - 必须包含‘全国包邮’、‘不退不换’、‘赠品说明’等标准条款模块。
                   - 结尾使用感叹号和短句营造紧迫感，呼吁立即行动。
                   - 整体语言口语化、热情，突出‘超值’、‘限量’、‘抢购’等概念。
                3. 变量处理：用户指令中的 {text_desc} 和 {image_desc} 是占位符，分别对应商品的核心文本描述和外观/场景描述。你需要将它们自然地融合到文案的合适位置，{text_desc} 主要用于功能卖点部分，{image_desc} 主要用于外观或使用场景描述部分。严禁修改或忽略这些变量。
                
                输出格式要求:
                纯文本
            """
              },
              {
                "role": "assistant",
                "content": f"""
                【超值特惠】智能WiFi天气时钟 多功能桌面摆件 高清主题+股票监控+性能显示（全新升级版）
                •智能天气显示：无需复杂代码，直接输入城市名即可实时显示天气、温度、湿度信息，生活出行一手掌握。
                •百变主题界面：内置12个高清主题，手机客户端一键切换，每天都有新感觉，打造专属你的桌面景观。
                •全能信息监控：独家支持股票行情（四大交易所）和电脑性能（CPU、内存占用）监控，工作娱乐两不误。
                •卓越显示品质：采用定制TFT屏幕，无漏光，显示清晰；外壳ABS注塑磨砂工艺，质感细腻，告别3D打印的粗糙感。
                •强大扩展功能：支持正倒计时、农历、500+动画、电子相册、夜间模式、千万种颜色自定义，固件可升级，玩法无限。
                产品包装：全新全套，含时钟主机、Type-C数据线、合格证、包装盒。
                采用H5编写控制端，安卓、苹果、电脑都能轻松配置，自主开发字库，中文显示无乱码。
                外壳小巧精致，尺寸仅4.5×3.5×3.9cm，不占空间，配色多样，完美融入任何桌面环境。
                
                •全国包邮：支持全国范围内的快递配送，买家无需承担运费。
                •不退不换：除功能问题外，本商品不支持退换货及售后服务，请确认需求后下单。
                •赠品说明：全新塑封包装，含数据线、合格证及磨砂保护袋（需要更多配件请咨询客服）。
                
                - 库存紧张，售完即止！标价即为实价，功能强大颜值高，买到就是赚到！ 立即下单，打造你的智能桌面中心！
            """
              },
            {
            "role": "user",
            "content": f"""
            请根据以下商品信息，撰写一份营销文案。
            
            商品标题：{text_desc}
            商品外观与场景描述：{image_desc}
        
            请参考目标案例的风格和结构进行创作。
            """
        }
        ],
            temperature=0.1
        )

        # response = client_ds.chat.completions.create(
        #     model="deepseek-chat",
        #     messages=[
        #         {"role": "user", "content": prompt}
        #     ]
        # )

        return clean_llm_response(response.choices[0].message.content)
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