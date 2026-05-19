import os
import subprocess
import sys

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import mysql.connector
import pymysql
from sqlalchemy import create_engine

# 导入标题生成模块
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'auto_shelving_goofish_web'))
from generate_title import title_generation
app = FastAPI()

# 必须配置跨域，否则前端 JS 无法调用接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库配置 (建议根据你的实际情况修改)
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "goofish_db"
}


# --- 1. 数据接口 (API) ---
engine = create_engine(f"mysql+pymysql://root:123456@localhost/goofish_db")

def get_db_data(date: str, category: str):
    query = """
    SELECT item_id, price, want_count, view_count, description, item_url 
    FROM goods 
    WHERE collect_date = %s AND category = %s
    """
    # 使用 engine 代替 conn
    df = pd.read_sql(query, engine, params=(date, category))
    return df


@app.get("/api/categories")
async def get_categories():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM goods WHERE category IS NOT NULL AND category != ''")
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/available-dates")
async def get_available_dates(category: str):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        sql = "SELECT DISTINCT collect_date FROM goods WHERE category = %s"
        cursor.execute(sql, (category,))
        dates = [str(row[0]) for row in cursor.fetchall()]
        conn.close()
        return dates
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calculate_hotness(df: pd.DataFrame):
    if df.empty:
        return df

    # --- 选品预处理 ---
    # 2. 设定选品门槛：想要人数太少的（如 < 5人）可能不具统计意义
    df = df[df['want_count'] >= 5].copy()

    if df.empty:
        return df

    # --- 核心指标计算 ---
    # 3. 平滑转化率计算 (防止低曝光带来的 100% 转化率干扰)
    # 公式：(想要数) / (浏览量 + 均值偏移)，这里给分母加一个常数 100
    df['cr'] = df['want_count'] / (df['view_count'] + 100)

    # 4. 选品权重重新分配
    # 选品模型更看重：转化效率 (CR) > 绝对意向人数 (Want) > 曝光总量 (View)
    W_WANT, W_CR, W_VIEW = 0.3, 0.5, 0.2

    # 5. 归一化处理
    for col in ['want_count', 'cr', 'view_count']:
        max_val = df[col].max()
        min_val = df[col].min()
        if max_val != min_val:
            df[f'norm_{col}'] = (df[col] - min_val) / (max_val - min_val)
        else:
            df[f'norm_{col}'] = 1 if max_val > 0 else 0

    # 6. 计算最终选品指数
    df['hotness_score'] = (W_WANT * df['norm_want_count'] +
                           W_CR * df['norm_cr'] +
                           W_VIEW * df['norm_view_count']) * 100

    # 返回结果，按选品得分降序
    return df.sort_values(by='hotness_score', ascending=False)


@app.post("/api/analysis/top-goods")
async def get_hot_goods(date: str = Query(...), keyword: str = Query(...)):
    try:
        # 获取原始数据
        raw_df = get_db_data(date, keyword)
        if raw_df.empty:
            return {"message": "未查询到相关数据", "data": []}

        # 构建计算模型
        result_df = calculate_hotness(raw_df)

        # 转换为 JSON 格式返回
        return {
            "date": date,
            "category": keyword,
            "count": len(result_df),
            "data": result_df.to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 2. 网页托管 (静态文件) ---
# 必须放在所有 API 路由之后
@app.get("/")
async def read_index():
    return FileResponse('index.html')


@app.get("/api/favorites")
async def get_favorites():
    """获取所有收藏商品及其详细信息"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # 先查询 favorites 表的所有字段（包括 ai_generated_title）
        sql = """
            SELECT f.id, f.item_id, f.ai_generated_title, f.source_url, f.status, f.remark, f.created_at,
                   g.description, g.price, g.item_url, g.want_count
            FROM favorites f
            JOIN goods g ON f.item_id = g.item_id
            ORDER BY f.created_at DESC
        """
        cursor.execute(sql)
        data = cursor.fetchall()

        # 为没有 AI 标题的商品生成标题
        for item in data:
            if not item.get('ai_generated_title'):
                # 如果数据库中没有 AI 标题，则生成并保存
                if item.get('description'):
                    try:
                        desc_preview = item['description'][:200] if len(item['description']) > 200 else item[
                            'description']
                        ai_title = title_generation(item['item_id'], desc_preview)

                        if ai_title:
                            item['ai_generated_title'] = ai_title
                            # 保存到数据库
                            update_sql = "UPDATE favorites SET ai_generated_title = %s WHERE item_id = %s"
                            cursor.execute(update_sql, (ai_title, item['item_id']))
                            conn.commit()
                        else:
                            item['ai_generated_title'] = item['description']
                    except Exception as e:
                        print(f"为商品 {item['item_id']} 生成标题失败：{e}")
                        item['ai_generated_title'] = item['description']
                else:
                    item['ai_generated_title'] = '-'
            # 确保每个 item 都有 ai_generated_title 字段
            if 'ai_generated_title' not in item:
                item['ai_generated_title'] = item.get('description', '-')

        conn.close()
        return data
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites/add")
async def add_favorite(item_id: str = Query(...)):
    """添加收藏"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # 使用 INSERT IGNORE 或 ON DUPLICATE KEY UPDATE 避免重复
        sql = "INSERT IGNORE INTO favorites (item_id, status) VALUES (%s, 0)"
        cursor.execute(sql, (item_id,))
        conn.commit()
        conn.close()
        return {"message": "收藏成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/favorites/update")
async def update_favorite(data: dict):
    """更新收藏信息（状态、货源、备注）"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        sql = """
            UPDATE favorites 
            SET status = %s, source_url = %s, remark = %s 
            WHERE item_id = %s
        """
        cursor.execute(sql, (data['status'], data['source_url'], data['remark'], data['item_id']))
        conn.commit()
        conn.close()
        return {"message": "更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/favorites/{item_id}")
async def delete_favorite(item_id: str):
    """取消收藏"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE item_id = %s", (item_id,))
        conn.commit()
        conn.close()
        return {"message": "删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/favorites/shelve/{item_id}")
async def start_shelving(item_id: str):
    """调用本地脚本执行上架任务"""
    try:
        # 这里指定你本地 python 解释器的路径和脚本路径
        # 注意：db_goods_shelving.py 内部需要支持接收参数或从数据库读 item_id
        script_path = r"/auto_shelving_goofish_web\db_goods_shelving.py"

        # 异步启动脚本（不阻塞 FastAPI），传入 item_id
        subprocess.Popen([r"E:\python.exe", script_path, item_id], shell=True)

        return {"status": "success", "message": f"商品 {item_id} 上架任务已启动"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 挂载当前目录下的静态文件 (js, css)
app.mount("/", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    print("🚀 系统已启动！")
    print("👉 请在浏览器访问: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)