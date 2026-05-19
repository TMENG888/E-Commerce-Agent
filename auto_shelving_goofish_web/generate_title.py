import pymysql
import requests
from zai import ZhipuAiClient
from base import Base

API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
base = Base()
client = ZhipuAiClient(api_key=API_KEY)

def get_goods_description(item_id):
    """从数据库获取指定 item_id 的商品信息"""
    connection = pymysql.connect(**base.DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            # SQL 查询语句
            sql = "SELECT description FROM `goods` WHERE `item_id` = %s"
            cursor.execute(sql, (item_id,))
            description = cursor.fetchone()
            return description[0] if description else ""
    finally:
        connection.close()


def title_generation(item_id,description=None):
    """依据商品描述生成电商标题"""
    if description is None:
        description = get_goods_description(item_id)

    prompt_text = f"""
       你是一位精通闲鱼、淘宝等电商平台的标题优化专家。
       任务：根据提供的【商品描述】和【商品图片】，生成一个极具吸引力的“爆款标题”。

       要求：
       1. 标题长度控制在 30-60 个汉字之间。
       2. 必须包含核心关键词、品牌（如果有）、成色、适用人群或场景。
       3. 语气要自然、真实，像个人卖家闲置转让，不要过于像广告。
       4. 适当加入一些热门流量词（如：包邮、急出、几乎全新、仅试用等），但要符合事实。
       5. 不要包含任何特殊符号（如【】、★等），只用中文和数字。

       【商品描述】：
       {description}

       请直接输出标题，不要包含“标题是：”等多余前缀。
       """
    try:
        response = client.chat.completions.create(
            model="GLM-4-Flash-250414",
            messages=[{"role": "user", "content": prompt_text}],
            stream=True,
            temperature=0.7,
            top_p=0.9
        )

        full_title = ""
        print("🚀 正在生成标题: ", end="")
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                full_title += content
                print(content, end="", flush=True)
        print("\n✅ 生成成功！")
        return full_title.strip()

    except Exception as e:
        print(f"❌ 生成标题失败: {str(e)}")
        return ""