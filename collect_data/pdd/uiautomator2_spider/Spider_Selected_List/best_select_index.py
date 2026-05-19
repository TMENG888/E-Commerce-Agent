import json
import re
from openai import OpenAI
import pymysql
from datetime import date

config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'pdd_db',
    'charset': 'utf8mb4'
}


def get_pdd_source_string():
    today = date.today().strftime('%Y-%m-%d')
    source = ""
    connection = pymysql.connect(**config)
    try:
        with connection.cursor() as cursor:
            sql = "SELECT rank_num, goods_message, price FROM pdd_rank_goods WHERE collect_date = %s ORDER BY rank_num ASC"
            cursor.execute(sql, (today,))
            results = cursor.fetchall()
            lines = [f"{row[0]}\t{row[1]}\t{row[2]}" for row in results]
            source = "\n".join(lines)
    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        connection.close()
    return source


def save_ai_response_to_db(text_content):
    json_pattern = r'\[\s*\{.*\}\s*\]'
    match = re.search(json_pattern, text_content, re.DOTALL)
    if not match:
        print("❌ 未在输出中找到有效的 JSON 选品数据")
        return

    try:
        products = json.loads(match.group())
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        insert_sql = "INSERT INTO selected_products (original_index, product_name, price, decision_reason) VALUES (%s, %s, %s, %s)"

        for item in products:
            cursor.execute(insert_sql, (
                item.get('index'), item.get('product_name'), item.get('price'), item.get('decision_reason')
            ))
        conn.commit()
        print(f"✅ 成功将 {len(products)} 条选品数据存入 selected_products 表！")
    except Exception as e:
        print(f"❌ 存储过程出错: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def get_pdd_source_string():
    # 获取当天日期
    today = date.today().strftime('%Y-%m-%d')

    source = ""
    connection = pymysql.connect(**config)

    try:
        with connection.cursor() as cursor:
            # 2. 编写 SQL 查询
            # 按照 collect_date 查询，并按排名 rank_num 升序排列
            sql = """
            SELECT rank_num, goods_message, price 
            FROM pdd_rank_goods 
            WHERE collect_date = %s 
            ORDER BY rank_num ASC
            """
            cursor.execute(sql, (today,))
            results = cursor.fetchall()

            # 3. 格式化为字符串字段
            # 格式：排名 商品信息 | 标签（如有） 价格
            lines = []
            for row in results:
                rank, message, price = row
                # 将每一行拼接成：1  商品名称  价格
                line = f"{rank}\t{message}\t{price}"
                lines.append(line)

            source = "\n".join(lines)

    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        connection.close()

    return source

# 核心修改：将大模型调用封装为函数，供主程序调用
def process_ai_selection(source_string):
    if not source_string:
        print("❌ 数据源为空，跳过 AI 分析")
        return

    OPENAI_API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://open.bigmodel.cn/api/paas/v4")

    # Messages
    messages = [
        {
        "role": "system",
        "content": f"""
        你是一位专业的闲鱼转销爆款选品分析师。你的任务是分析给定的商品数据，从中挑选出最适合在闲鱼平台进行转销的爆款商品。你需要综合考虑以下维度：
        1. **品牌溢价与信任度**：知名品牌（如小米、华为、联想、绿联等）在闲鱼上更容易获得买家信任，转售差价空间更大。
        2. **价格优势**：对比该商品在主流电商平台（京东、天猫、拼多多）的日常售价，进货价是否有显著价差（通常20%以上）。
        3. **市场需求与时效性**：商品是否属于当前季节（如夏季风扇）、技术热点（如WiFi 7）、或特定人群（学生、家长、游戏玩家）的刚需。
        4. **商品属性与卖点**：商品标题中的关键词（如“官方旗舰店”、“正品险”、“即将售罄”、“立减”等）反映了其市场热度与促销力度。
        5. **闲鱼销售策略**：思考如何包装商品（如“搬家转让”、“抽奖中的”、“毕业闲置”），以及如何定价、捆绑销售（如打印机+打印纸）来提升客单价和转化率。
    
        请基于以上原则，从提供的商品列表中，挑选出8个最具潜力的闲鱼转销爆款。对于每个选品，你需要给出：
        - 商品在列表中的索引号（index）
        - 商品名称（product_name）
        - 详细的选品理由（decision_reason），包括价格分析、目标人群、销售话术建议等。
    
        输出格式为JSON数组，每个元素包含index、product_name、price、decision_reason三个字段。
    
        输出格式要求:
        JSON
        """
        },
        {
            "role": "assistant",
            "content": """
        [
          {
            "index": 4,
            "product_name": "喵喵机P1S错题打印机",
            "price": 78.1,
            "decision_reason": "闲鱼学生流量巨大，错题打印机是初高中生的刚需。该产品单价适中，且喵喵机品牌自带流量，二次转卖时以『备考转让』或『年会抽奖』为话术，极易出单且具备一定溢价空间。"
          },
          {
            "index": 17,
            "product_name": "小米路由器WiFi7 BE3600",
            "price": 134.9,
            "decision_reason": "WiFi 7 是当前网络设备的热点关键词。134.9元的拼多多价格极具竞争力，而闲鱼用户对小米品牌的认可度极高。此款路由器适合以『升级换代闲置』为名进行二次销售，利润空间稳健。"
          },
          {
            "index": 20,
            "product_name": "小米米家精修螺丝刀套装",
            "price": 61.9,
            "decision_reason": "米家螺丝刀是数码圈的『硬通货』。其工业设计感强，深受闲鱼男性用户喜爱。61.9元的进货价对比其89.9元的官方售价有明显优势，适合长期挂载，作为引流款或稳定出货款。"
          },
          {
            "index": 32,
            "product_name": "大眼橙C3Air高亮版投影仪",
            "price": 718.89,
            "decision_reason": "投影仪是闲鱼『宿舍神器』类目的常青树。大眼橙品牌在投影圈有一定知名度，该价位段在闲鱼二级市场非常受租房党和大学生欢迎，单笔利润相对较高。"
          },
          {
            "index": 41,
            "product_name": "睿量USB夹子小风扇",
            "price": 27.99,
            "decision_reason": "考虑到当前是4月底，夏季消暑产品即将进入爆发期。夹子风扇场景适应性强（宿舍、桌面），属于典型的低单价、高频次走量款，适合在闲鱼通过低价策略快速积累信用评价。"
          },
          {
            "index": 56,
            "product_name": "汉印MT610家用作业打印机",
            "price": 178,
            "decision_reason": "针对闲鱼上的家长群体。热敏打印机免墨水的特性非常吸引『省心』型用户。汉印在便携打印领域口碑不错，178元的成本价在闲鱼同型号对比中具有极强杀伤力。"
          },
          {
            "index": 68,
            "product_name": "小米显示器挂灯1S",
            "price": 169.9,
            "decision_reason": "桌面美学（Setup）类产品的闲鱼需求极其稳定。米家挂灯1S由于支持智能联动，是很多搭建桌面玩家的首选。169.9元的价格相比官网有优势，属于搜索意向非常明确的高转化产品。"
          },
          {
            "index": 70,
            "product_name": "智能可视挖耳勺",
            "price": 29.9,
            "decision_reason": "属于『新奇特』且带有个人护理属性的小家电。这类产品在闲鱼通过短视频或动图展示功能后，极易吸引冲动型消费。进货成本低，风险小，适合作为店铺的辅助选品。"
          }
        ]
        """
        },
        {
            "role": "user",
            "content": f"""
            请分析以下商品数据，并按照系统指令的要求，挑选出8个最适合在闲鱼转销的爆款商品。

            商品列表：
            {source_string}
        """
        }
    ]

    print("🤖 AI 正在深度思考分析中...")
    response = client.chat.completions.create(
        model="GLM-5",
        messages=messages,
        stream=False
    )

    # 存入数据库
    save_ai_response_to_db(response.choices[0].message.content)