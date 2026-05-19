"""
拼多多反检测统一模块
所有 Playwright 页面都必须通过此模块初始化
"""
import asyncio
import random
import time
from collections import deque

# ========== 1. 反检测脚本注入 ==========

STEALTH_JS = """
// ===== Playwright 变量清除 =====
// 拼多多 BotDetector 检测: __PW_inspect, __pw_manual, __playwright, /^__playwright_/, /^__pw_/
// 必须在页面最早阶段拦截这些变量

// 方案: 遍历 window 属性时过滤掉 Playwright 变量
const originalDefineProperty = Object.defineProperty;
const patchedKeys = [];

// 劫持 Object.defineProperty 阻止 Playwright 注入变量
Object.defineProperty = function(obj, prop, descriptor) {
    if (obj === window && typeof prop === 'string') {
        if (prop.startsWith('__playwright') || prop.startsWith('__pw_') || prop.startsWith('__PW_')) {
            patchedKeys.push(prop);
            return obj; // 阻止定义，但不报错
        }
    }
    return originalDefineProperty.call(this, obj, prop, descriptor);
};

// 延迟恢复，让 Playwright 注入失败
setTimeout(() => {
    Object.defineProperty = originalDefineProperty;
    // 删除可能已经注入的变量
    patchedKeys.forEach(key => {
        try { delete window[key]; } catch(e) {}
    });
    try {
        Object.keys(window).forEach(key => {
            if (typeof key === 'string' && 
                (key.startsWith('__playwright') || key.startsWith('__pw_') || key.startsWith('__PW_'))) {
                delete window[key];
            }
        });
    } catch(e) {}
}, 0);

// ===== navigator.webdriver =====
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// ===== Chrome API 伪造 =====
if (!window.chrome) window.chrome = {};
window.chrome.runtime = {
    connect: function(){}, sendMessage: function(){},
    onMessage: { addListener: function(){} }, id: undefined
};
window.chrome.loadTimes = function(){ return {}; };
window.chrome.csi = function(){ return {}; };
window.chrome.app = {
    isInstalled: false,
    InstallState: { DISABLED:'disabled', INSTALLED:'installed', NOT_INSTALLED:'not_installed' },
    RunningState: { CANNOT_RUN:'cannot_run', READY_TO_RUN:'ready_to_run', RUNNING:'running' }
};

// ===== Plugins 伪造 =====
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            { name:'Chrome PDF Plugin', filename:'internal-pdf-viewer',
              description:'Portable Document Format' },
            { name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',
              description:'' },
            { name:'Native Client', filename:'internal-nacl-plugin',
              description:'' }
        ];
        arr.refresh = () => {};
        return arr;
    }
});

// ===== Languages =====
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en-US', 'en']
});

// ===== productSub =====
Object.defineProperty(navigator, 'productSub', {
    get: () => '20030107'
});

// ===== WebGL 指纹伪装 =====
const hookWebGL = (proto) => {
    const orig = proto.getParameter;
    proto.getParameter = function(param) {
        if (param === 0x9245) return 'Apple Inc.';     // UNMASKED_VENDOR_WEBGL
        if (param === 0x9246) return 'Apple GPU';       // UNMASKED_RENDERER_WEBGL
        return orig.call(this, param);
    };
};
if (typeof WebGLRenderingContext !== 'undefined') hookWebGL(WebGLRenderingContext.prototype);
if (typeof WebGL2RenderingContext !== 'undefined') hookWebGL(WebGL2RenderingContext.prototype);

// ===== Permissions API =====
const origPermQuery = window.navigator.permissions.query.bind(window.navigator.permissions);
window.navigator.permissions.query = (params) => {
    if (params.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission });
    }
    return origPermQuery(params);
};

// ===== 硬件信息伪装 =====
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 4 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });

// ===== 隐藏 CDP 连接痕迹 =====
// 移除 Playwright 在 console 中留下的标记
const origConsoleDebug = console.debug;
console.debug = function() {
    const args = Array.from(arguments);
    if (args.some(a => typeof a === 'string' && a.includes('Playwright'))) return;
    origConsoleDebug.apply(console, arguments);
};
"""


# ========== 2. 人性化鼠标操作 ==========

class HumanMouse:
    """模拟真实鼠标轨迹和点击行为"""

    def __init__(self, page):
        self.page = page
        self._last_x = random.randint(50, 300)
        self._last_y = random.randint(100, 600)

    async def move_to(self, x: float, y: float, steps: int = None):
        """带贝塞尔曲线轨迹的鼠标移动"""
        if steps is None:
            distance = ((x - self._last_x) ** 2 + (y - self._last_y) ** 2) ** 0.5
            steps = max(8, min(30, int(distance / 20)))

        for i in range(steps):
            t = i / steps
            # 贝塞尔曲线 + 高斯抖动
            nx = self._last_x + (x - self._last_x) * t + random.gauss(0, 1.5)
            ny = self._last_y + (y - self._last_y) * t + random.gauss(0, 1.5)
            await self.page.mouse.move(nx, ny)
            await asyncio.sleep(random.uniform(0.005, 0.025))

        self._last_x = x
        self._last_y = y

    async def click(self, x: float, y: float):
        """✅ 带完整轨迹的点击 — 替换所有 page.mouse.click()"""
        # 1. 先移动到目标位置
        await self.move_to(x, y)
        # 2. 人类反应时间停顿
        await asyncio.sleep(random.uniform(0.05, 0.2))
        # 3. 执行点击
        await self.page.mouse.click(x, y)

    async def click_element(self, locator):
        """✅ 带完整轨迹的元素点击 — 替换所有 locator.click()"""
        box = await locator.bounding_box()
        if not box:
            # fallback：直接用 locator.click 但先滚动到可见
            await locator.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.3, 0.8))
            box = await locator.bounding_box()
            if not box:
                await locator.click()
                return

        # 目标点加随机偏移
        tx = box['x'] + box['width'] * random.uniform(0.25, 0.75)
        ty = box['y'] + box['height'] * random.uniform(0.25, 0.75)
        await self.click(tx, ty)


# ========== 3. 人性化滚动 ==========

async def human_scroll(page, direction='down', distance=None, step_range=None):
    """✅ 替换所有 page.mouse.wheel(0, N) — 模拟人类滚动"""
    if distance is None:
        distance = random.randint(150, 600)
    if step_range is None:
        step_range = (5, 12)

    steps = random.randint(*step_range)
    step_dist = distance / steps

    for i in range(steps):
        actual = step_dist * random.uniform(0.3, 1.7)  # 每步距离有波动
        delta = actual if direction == 'down' else -actual
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.03, 0.18))

    # 阅读停留
    await asyncio.sleep(random.uniform(0.5, 2.5))


# ========== 4. 人性化延迟 ==========

async def human_delay(min_s=2, max_s=8, fatigue_count=0):
    """✅ 替换所有 asyncio.sleep(固定值) — 正态分布 + 疲劳递增"""
    mu = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    delay = random.gauss(mu, sigma)
    delay = max(min_s, min(max_s, delay))
    # 疲劳效应：操作越多越慢
    delay += min(fatigue_count * 0.1, 3)
    await asyncio.sleep(delay)


# ========== 5. 限流器 ==========

class RateLimiter:
    """拼多多请求频率限制器"""

    def __init__(self):
        self.limits = {
            'product_click': {'window': 300, 'max': 8},  # 5分钟≤8次商品点击
            'search': {'window': 300, 'max': 4},  # 5分钟≤4次搜索
            'sku_click': {'window': 120, 'max': 15},  # 2分钟≤15次SKU点击
            'page_navigate': {'window': 300, 'max': 10},  # 5分钟≤10次页面跳转
            'image_download': {'window': 60, 'max': 20},  # 1分钟≤20张图片
        }
        self.history = {k: deque() for k in self.limits}

    def can_proceed(self, action: str) -> bool:
        config = self.limits.get(action)
        if not config:
            return True
        now = time.time()
        while self.history[action] and self.history[action][0] < now - config['window']:
            self.history[action].popleft()
        return len(self.history[action]) < config['max']

    async def wait_if_needed(self, action: str):
        while not self.can_proceed(action):
            wait = random.uniform(20, 60)
            print(f"  ⏳ {action} 限流等待 {wait:.0f}s")
            await asyncio.sleep(wait)
        self.history[action].append(time.time())


# ========== 6. 页面初始化 ==========

async def setup_stealth_page(context) -> 'Page':
    """✅ 创建带完整反检测的页面 — 替换 context.new_page()"""
    page = await context.new_page()
    # 注入反检测脚本（必须在任何页面加载前）
    await page.add_init_script(STEALTH_JS)
    # 可选：同时注入 stealth.min.js 作为补充
    await page.add_init_script(path=r'/stealth.min.js')
    return page


# 全局限流器实例
rate_limiter = RateLimiter()
