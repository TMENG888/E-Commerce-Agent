import uiautomator2 as u2
from paddleocr import PaddleOCR
import os
import logging

logging.getLogger("paddlex").setLevel(logging.ERROR)


# 1. 初始化 (使用你当前环境下生效的参数)
ocr = PaddleOCR(use_textline_orientation=True, lang="ch")

d = u2.connect("172.20.10.4:42361")

# 2. 截图
img_path = "screen.jpg"
d.screenshot(img_path)

# 3. 执行预测 (注意这里改成了 predict，且去掉了 cls)
print("正在通过 PP-OCRv5 识别内容...")
# 新版返回的是一个 result 列表，每个元素代表一张图的识别结果
output = ocr.predict(img_path)

# 4. 解析结果并点击
target_text = "10.6"
found = False

for res in output:
    texts = res.get('rec_texts', [])
    polygons = res.get('dt_polys', [])

    for i, text in enumerate(texts):
        if target_text in text:
            # 确保索引在 polygons 范围内，增加鲁棒性
            if i < len(polygons):
                poly = polygons[i]

                # poly 通常是 4 个点的数组: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                # 取左上角和右下角的平均值得到中心点
                center_x = int((poly[0][0] + poly[2][0]) / 2)
                center_y = int((poly[0][1] + poly[2][1]) / 2)

                print(f"找到目标：{text}, 执行点击坐标: ({center_x}, {center_y})")
                d.click(center_x, center_y)

                found = True
                d(description="收藏").click()
                break
    if found: break

if not found:
    print(f"未能在屏幕上匹配到关键词: {target_text}")