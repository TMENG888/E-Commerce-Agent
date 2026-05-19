import time

from fastapi import FastAPI, Request
import uvicorn
import re

app = FastAPI()
latest_sms = {"code": None, "time": 0}


@app.post("/sms")
async def receive_sms(request: Request):
    global latest_sms
    data = await request.json()
    content = data.get("content", "")

    # ... 正则匹配逻辑不变 ...
    code_match = re.search(r'(?<!\d)\d{4,6}(?!\d)', content)

    if code_match:
        code = code_match.group()
        # 更新全局字典
        latest_sms["code"] = code
        latest_sms["time"] = time.time()  # 记录收到时间
        print(f"✅ 已存入最新提取码: {code}")
    else:
        print(f"ℹ️ 收到普通短信，未识别出验证码。")


@app.get("/get_code")
async def get_code():
    global latest_sms
    # 如果验证码是 60 秒内收到的，则返回；否则返回 None
    if time.time() - latest_sms["time"] < 60:
        return {"code": latest_sms["code"]}
    return {"code": None}


if __name__ == "__main__":
    # 启动服务器，监听本地 8080 端口
    # 注意：手机和电脑需在同一局域网下
    uvicorn.run(app, host="0.0.0.0", port=8080)