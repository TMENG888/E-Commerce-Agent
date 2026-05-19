# Verification_code.py
import requests
import base64

API_KEY = "01fd01d3204444ed9ca4908161f797f1.pyaYzY1m1PNchN4z"
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def recognize_captcha(image_path):
    """识别指定路径的验证码图片"""
    img_base64 = encode_image(image_path)
    payload = {
        "model": "glm-4v-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别并直接输出图片中的验证码字符。如果是英文字母，请区分大小写。不要输出任何多余的解释文字。"},
                    {"type": "image_url", "image_url": {"url": f"{img_base64}"}}
                ]
            }
        ],
        "stream": False,
        "temperature": 0.1 
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        if "error" not in res_json:
            result = res_json['choices'][0]['message']['content']
            return result.strip()
        return "识别失败"
    except Exception as e:
        return f"请求异常: {str(e)}"