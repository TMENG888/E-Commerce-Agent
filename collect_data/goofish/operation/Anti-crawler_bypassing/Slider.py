import asyncio
import os

import cv2
import numpy as np
from playwright.sync_api import sync_playwright
from base import Base
import pyautogui
import time
import random


def get_slider_coordinate_opencv():
    """使用 OpenCV 模板匹配定位滑块中心"""
    # 1. 全屏截图并转换为 OpenCV 格式
    screenshot = pyautogui.screenshot()
    # 将 PIL 图片转换为 numpy 数组 (RGB -> BGR 以适应 OpenCV)
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    # 2. 读取滑块素材模板
    template_path = "slider_material.png"  # 你的滑块素材
    if not os.path.exists(template_path):
        print(f"❌ 找不到素材图: {template_path}")
        return None

    template = cv2.imread(template_path)
    # 获取模板的宽高
    h, w = template.shape[:2]

    # 3. 执行模板匹配
    # 使用 TM_CCOEFF_NORMED 算法，对光照变化有一定鲁棒性
    res = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)

    # 获取匹配度最高的坐标
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    # 设置匹配阈值（建议 0.7 - 0.9 之间）
    threshold = 0.8
    if max_val < threshold:
        print(f"⚠️ 未能精准定位滑块，最高匹配度仅为: {max_val:.2f}")
        return None

    # max_loc 是匹配区域的左上角坐标 (x, y)
    top_left = max_loc
    # 计算中心点坐标
    center_x = top_left[0] + w // 2
    center_y = top_left[1] + h // 2

    print(f"🎯 OpenCV 定位成功! 匹配度: {max_val:.2f}, 坐标: [{center_x}, {center_y}]")
    return [center_x, center_y]


def solve_captcha():
    """执行滑块破解"""
    print("📸 正在截屏分析位置...")
    point = get_slider_coordinate_opencv()

    if not point or len(point) != 2:
        print("❌ AI 未能返回有效坐标")
        return

    start_x, start_y = point
    # 闲鱼滑块通常向右滑动约 300 像素
    distance = 350

    print(f"🎯 目标锁定：({start_x}, {start_y})，准备滑动...")

    # --- pyautogui 物理模拟 ---
    # 1. 移动到滑块
    pyautogui.moveTo(start_x, start_y, duration=random.uniform(0.3, 0.6))

    # 2. 按下鼠标
    pyautogui.mouseDown()

    # 3. 模拟人类滑动轨迹 (分段滑动)
    current_dist = 0
    while current_dist < distance:
        # 随机步长
        step = random.randint(15, 40)
        current_dist += step
        if current_dist > distance: current_dist = distance

        # 增加 Y 轴微小抖动，模拟手抖
        pyautogui.moveTo(
            start_x + current_dist,
            start_y + random.randint(-2, 2),
            duration=random.uniform(0.05, 0.15)
        )

    # 4. 释放鼠标
    pyautogui.mouseUp()
    print("✨ 滑动任务完成")

