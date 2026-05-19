import asyncio
import json
import os
import time
import re
import requests
from decimal import Decimal
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

PUBLISH_URL = "https://seller.goofish.com/?site=COMMONPRO#/seller-item/publish"
GOODS_MANAGE_URL = "https://seller.goofish.com/?site=COMMONPRO#/seller-item/goods-manage"

class GoofishIntegrator:
    def __init__(self):
        self.cookie_path_crawl = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_cookies.json"
        self.spec_image_folder = r"C:\Users\31193\Pictures\商品规格图"
        self.base_image_folder = r"C:\Users\31193\Pictures\商品主图"
        self.chrome_debug_url = "http://localhost:9222"

    def extract_clean_text(self, html_content):
        import re
        from bs4 import BeautifulSoup

        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. 把所有的 <br> 标签替换为换行符 \n
        for br in soup.find_all('br'):
            br.replace_with('\n')

        # 2. 核心修改：寻找所有“内部没有文本”的空 span 标签
        for span in soup.find_all('span'):
            if not span.get_text(strip=True):
                if span.parent:
                    span.replace_with('\n')

        # 3. 提取纯文本（此时所有的换行符已经安全植入了）
        text = soup.get_text(separator='', strip=False)

        # 4. 清理残留的不可见特殊字符，保留干净的空格
        text = text.replace('\u200b', '').replace('\xa0', ' ')

        # 6. 【可选】对连续的多余空行进行合理压缩（比如超过2个连续换行压缩为2个）
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text

    def clean_description(self, desc):
        """
        清洗商品描述：移除emoji、移除末尾的'展开'，保留换行符
        """
        # 1. 移除所有 emoji（覆盖几乎所有类型 ✔ ✅ ★ ✨ 等）
        emoji_pattern = re.compile(
            r"""
            [\u2600-\u26FF]          # 杂项符号（☀️★✏️）
            | [\u2700-\u27BF]        # 装饰符号 ✔ ✅ ❌
            | [\uE000-\uF8FF]        # 私人使用区
            | [\u200D]               # 零宽连接符
            | [\uFE0E\uFE0F]         # 变体选择符
            | [\U0001F600-\U0001F64F]  # 表情脸
            | [\U0001F300-\U0001F5FF]  # 天气、物品
            | [\U0001F680-\U0001F6FF]  # 交通
            | [\U0001F1E0-\U0001F1FF]  # 国旗
            """,
            flags=re.UNICODE | re.VERBOSE
        )
        desc = emoji_pattern.sub("", desc)

        # 2. 移除末尾的 "展开"
        desc = desc.rstrip("展开")

        # 3. 清理可能残留的空行（可选）
        desc = "\n".join([line.strip() for line in desc.splitlines()])

        return desc

    async def crawl_single_item(self, item_id):
        """采集商品完整信息，包括规格数据"""
        url = f"https://www.goofish.com/item?id={item_id}"
        print(f"🔍 开始采集商品: {item_id}")

        print("\n🔗 检查浏览器状态...")
        if not ensure_chrome_running():
            return

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.chrome_debug_url)
            context = browser.contexts[0]

            with open(self.cookie_path_crawl, "r", encoding="utf-8") as f:
                await context.add_cookies(json.load(f))

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            if await page.get_by_text("糟糕！宝贝被删掉了").is_visible():
                print(f"❌ 商品 {item_id} 已被删除")
                return None

            html = await page.content()

            price_match = re.search(r'class="price--[^"]*"[^>]*>([\d.]+)', html)
            price = float(price_match.group(1)) if price_match else 0.0

            desc_match = re.search(r'class="desc--[^>]*">([\s\S]*?)</div>', html)

            if "买家可退货且运费由卖家承担" in desc_match.group(1):
                desc_match = re.search(
                    r'class="notLoginContainer--hQCDYhxp"[\s\S]*?text-align: justify;">([\s\S]*?)</div>\s*</div>', html)
                description = self.extract_clean_text(desc_match.group(1))
                clean_description = self.clean_description(description)
            else:
                description = self.extract_clean_text(desc_match.group(1))
                clean_description = self.clean_description(description)

            # 1. 拿稳定的缩略图局部容器（这个容器里面绝对能拿齐所有主图，不会被提前截断）
            image_container_match = re.search(
                r'<div class="item-main-window-list--[^"]+".*?>(.*?)<div class="item-main-window-carousel--', html,
                re.S).group(1)
            image_match = re.findall(r'src="//([^"]+)', image_container_match)

            # 2. 转换为完整的 https 链接并去重
            raw_urls = [f"https://{url}" for url in list(dict.fromkeys(image_match))]

            # 3. 【核心优化】智能替换：不论是 220x 还是其他尺寸，统一转换成你需要的高清规格
            image_urls = []
            for url in raw_urls:
                if "220x10000Q90" in url:
                    high_res = url.replace("220x10000Q90", "790x10000Q90")
                elif "_220x" in url:
                    high_res = re.sub(r'_\d+x\d+.*?\.', '_790x10000Q90.', url)
                else:
                    high_res = url
                image_urls.append(high_res)

            print(f"📦 基础信息采集完成，开始采集规格数据...")
            buy_btn = page.locator('a.buy--MCbvZ6Lw').filter(has_text='立即购买')
            await buy_btn.click()
            print("🖱️ 已点击立即购买，进入规格选择页面")
            await asyncio.sleep(3)

            spec_options = page.locator('span.option--DTi05xzX')
            spec_count = await spec_options.count()
            print(f"📋 发现 {spec_count} 个规格选项")

            if spec_count == 0:
                await page.close()
                return {
                    "item_id": item_id,
                    "price": price,
                    "description": clean_description,
                    "image_urls": image_urls,
                    "specs": []
                }

            specs = []
            spec_image_list = []  # 存所有规格图 URL

            for i in range(spec_count):
                try:
                    spec_option = spec_options.nth(i)
                    spec_text = await spec_option.text_content()
                    spec_text = spec_text.strip() if spec_text else ""

                    is_disabled = await spec_option.get_attribute('style') or ''
                    if 'rgb(182, 182, 182)' in is_disabled or 'color: rgb(182, 182, 182)' in is_disabled:
                        print(f"   规格 {i + 1}: {spec_text} (不可选，已禁用)")
                        continue
                    else:
                        await spec_option.click()
                        await asyncio.sleep(3)
                        print(f"   点击规格 {i + 1}: {spec_text}")

                    spec_image_url = None
                    try:
                        pic_locator = page.locator(".picture--YVPEF71r img")
                        spec_image_url = await pic_locator.nth(1).get_attribute("src")
                        # 补全 https
                        if spec_image_url and not spec_image_url.startswith("http"):
                            spec_image_url = "https:" + spec_image_url
                    except Exception as img_e:
                        print(f"      ⚠️ 获取规格图片失败: {img_e}")

                    # 获取价格
                    spec_price = await page.locator(".price--Gj3li1qD span:nth-child(2)").inner_text()

                    spec_data = {
                        "spec_name": spec_text,
                        "price": spec_price,
                        "image_url": spec_image_url,
                        "path": None
                    }
                    specs.append(spec_data)

                    # 加入统一下载列表
                    if spec_image_url:
                        spec_image_list.append({
                            "url": spec_image_url,
                            "spec_name": spec_text,
                            "index": i
                        })

                except Exception as spec_e:
                    print(f"   ❌ 处理规格 {i + 1} 失败: {spec_e}")

            for spec in specs:
                if spec["image_url"]:
                    safe_name = spec["spec_name"].replace('/', '_').replace('+', '_plus_').replace('*', '_star_')
                    spec["path"] = os.path.join(self.spec_image_folder, str(item_id), f"{safe_name}.jpg")

            await page.close()

            print(f"\n✅ 商品 {item_id} 采集完成，共获取 {len(specs)} 个有效规格")
            return {
                "item_id": item_id,
                "price": price,
                "description": clean_description,
                "image_urls": image_urls,
                "specs": specs,
                "spec_image_list": spec_image_list
            }

    def download_images(self, item_id, urls):
        """下载商品主图"""
        folder = os.path.join(self.base_image_folder, str(item_id))
        os.makedirs(folder, exist_ok=True)
        print(f"📂 图片下载目录: {folder}")

        headers = {"User-Agent": "Mozilla/5.0"}
        for i, url in enumerate(urls):
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    with open(os.path.join(folder, f"{i + 1}.jpg"), 'wb') as f:
                        f.write(res.content)
            except Exception as e:
                print(f"图片下载出错: {e}")
        return folder

    def download_spec_images(self, item_id, spec_images):
        """批量下载规格图片"""
        folder = os.path.join(self.spec_image_folder, str(item_id))
        os.makedirs(folder, exist_ok=True)
        headers = {"User-Agent": "Mozilla/5.0"}

        for item in spec_images:
            url = item["url"]
            spec_name = item["spec_name"]
            try:
                # 文件名安全处理
                safe_name = spec_name.replace('/', '_').replace('+', '_plus_').replace('*', '_star_')
                filename = f"{safe_name}.jpg"
                filepath = os.path.join(folder, filename)

                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(res.content)
                    print(f"      ✔️ 规格图下载完成: {filename}")
            except Exception as e:
                print(f"      ⚠️ 下载失败: {e}")
        return folder

def ensure_chrome_running():
    """确保 Chrome 浏览器以调试模式运行"""
    import socket
    import subprocess

    port = 9222
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\selenium\automation_profile"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        is_open = s.connect_ex(('127.0.0.1', port)) == 0

    if is_open:
        print(f"✅ 端口 {port} 已开启，准备接管现有浏览器实例...")
    else:
        print(f"🌐 端口 {port} 未开启，正在启动新浏览器实例...")
        command = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        try:
            subprocess.Popen(command)
            time.sleep(3)
            print("✅ 浏览器启动成功")
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            return False
    return True


async def shelve_single_goods(page, goods_id, goods_data):
    """上架单个商品，使用新平台的规格数据"""

    print(f"\n📦 处理商品: {goods_id}")
    publish_success = False

    description = goods_data.get('description', '')
    specs = goods_data.get('specs', [])

    print(f"   ├── 描述长度: {len(description)}")
    print(f"   └── 规格数量: {len(specs)}")

    if description:
        print("📝 填写商品描述...")
        desc_input = page.locator('[data-placeholder="描述一下宝贝的品牌型号、货品来源..."]')
        await desc_input.click()
        await asyncio.sleep(1)
        await page.keyboard.type(description)
        await asyncio.sleep(2)

    if len(specs) != 1 and len(specs) > 0:
        print("🔧 填写规格信息...")

        add_btn = page.locator('button.addBtn--aeORl7oU')
        await add_btn.click()
        await asyncio.sleep(2)

        select_div = page.locator('#itemProperties_0_propertyName')
        await select_div.click()
        await asyncio.sleep(2)

        color_option = page.locator('div.ant-select-item-option-content', has_text='颜色')
        await color_option.click()
        await asyncio.sleep(1)

        for idx, spec in enumerate(specs):
            spec_name = spec.get("spec_name", "")
            spec_price = spec.get("price", 0)
            print(f"      └── 规格{idx+1}: {spec_name}, 价格: {spec_price}")

            input_selector = f'input[id="itemProperties_0_propertyValues_{idx}_propertyValue"]'
            input_element = page.locator(input_selector)

            await input_element.click()
            await asyncio.sleep(0.5)
            await input_element.fill(spec_name)
            await asyncio.sleep(1)

            price_input = page.locator(f'input[id="itemSkuList_{idx}_price"]')
            if await price_input.count() > 0:
                await price_input.click()
                await asyncio.sleep(0.5)
                await price_input.fill(str(spec_price))
                await asyncio.sleep(0.5)
            else:
                price_inputs = page.locator('span.ant-input-affix-wrapper input.ant-input')
                if await price_inputs.count() > idx:
                    await price_inputs.nth(idx).click()
                    await asyncio.sleep(0.5)
                    await price_inputs.nth(idx).fill(str(spec_price))
                    await asyncio.sleep(0.5)
                else:
                    print(f"      ⚠️ 未找到第 {idx+1} 个价格输入框")

            stock_input = page.locator(f'input[id="itemSkuList_{idx}_quantity"]')
            if await stock_input.count() > 0:
                await stock_input.click()
                await asyncio.sleep(0.5)
                await stock_input.fill("9")
                await asyncio.sleep(0.5)
            else:
                stock_inputs = page.locator('input[placeholder="0"][min="0"]')
                await stock_inputs.nth(idx).click()
                await asyncio.sleep(0.5)
                await stock_inputs.nth(idx).fill("3")
                await asyncio.sleep(0.5)

        print("🖼️  开始上传规格图片...")
        upload_divs = page.locator('div.inputImgUpload--XnhX4Utt')
        upload_count =await upload_divs.count()

        for idx, spec in enumerate(specs):
            if idx >= upload_count:
                print(f"⚠️ 图片上传元素数量不足，只有 {upload_count} 个，跳过第 {idx+1} 个规格的图片上传")
                continue

            image_path = spec.get("path", "")
            if not image_path or not os.path.exists(image_path):
                print(f"⚠️ 规格 {idx+1} 的图片路径不存在或为空: {image_path}")
                continue

            print(f"      └── 上传规格 {idx+1} 的图片: {os.path.basename(image_path)}")

            try:
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    await upload_divs.nth(idx).click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(image_path)
                print(f"      ✅ 图片上传成功: {os.path.basename(image_path)}")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"      ❌ 图片上传失败: {e}")
    else:
        print("   └── 该商品仅有一个规格，填写售价、原价和库存")

        if len(specs) == 1:
            spec = specs[0]
            spec_price = spec.get("price", 0)
            original_price = round(spec_price * 2.5, 2)

            print(f"      └── 规格价格: {spec_price}, 原价: {original_price}, 库存: 3")

            try:
                price_inputs = page.locator('span.ant-input-affix-wrapper input.ant-input')
                if price_inputs.count() > 0:
                    await price_inputs.first.click()
                    await asyncio.sleep(0.5)
                    await price_inputs.first.fill(str(spec_price))
                    await asyncio.sleep(0.5)
                    print(f"      ✅ 已填写售价: {spec_price}")
                else:
                    print(f"      ⚠️ 未找到售价输入框")
            except Exception as e:
                print(f"      ❌ 填写售价失败: {e}")

            try:
                all_price_inputs = page.locator('input[placeholder="0.00"], input[min="0"]')
                if all_price_inputs.count() >= 2:
                    await all_price_inputs.nth(1).click()
                    await asyncio.sleep(0.5)
                    await all_price_inputs.nth(1).fill(str(original_price))
                    await asyncio.sleep(0.5)
                    print(f"      ✅ 已填写原价: {original_price}")
            except Exception as e:
                print(f"      ⚠️ 填写原价失败: {e}")

            try:
                stock_inputs = page.locator('input[placeholder="1"], input[placeholder="0"][min="0"]')
                if stock_inputs.count() > 0:
                    await stock_inputs.first.click()
                    await asyncio.sleep(0.5)
                    await stock_inputs.first.fill("3")
                    await asyncio.sleep(0.5)
                    print(f"      ✅ 已填写库存: 3")
                else:
                    print(f"      ⚠️ 未找到库存输入框")
            except Exception as e:
                print(f"      ❌ 填写库存失败: {e}")

    print("🖼️ 开始上传商品主图...")
    goods_image_folder = os.path.join(r"C:\Users\31193\Pictures\商品主图", str(goods_id))

    if os.path.exists(goods_image_folder):
        # 1. 搜集该目录下所有的 .jpg 图片的绝对路径，组成一个 List
        jpg_files = [f for f in os.listdir(goods_image_folder) if f.lower().endswith('.jpg')]
        jpg_files.sort()

        if jpg_files:
            print(f"   └── 发现 {len(jpg_files)} 张图片，准备执行一键全选上传...")

            # 组合成完整的绝对路径列表
            all_image_paths = [os.path.join(goods_image_folder, name) for name in jpg_files]

            # 2. 定位第一个上传入口
            first_upload_div = page.locator('div.upload-item--VvK_FTdU').first

            try:
                # 3. 触发文件选择器（只需要触发一次点击即可）
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    await first_upload_div.click()
                file_chooser = await fc_info.value

                # 4. 【核心改动】直接将一整个绝对路径的列表传进去，模拟人工的 Ctrl+A 全选
                await file_chooser.set_files(all_image_paths)
                print(f"   ✅ 一键全选上传指令已发送，成功提交 {len(jpg_files)} 张图片！")

                # 给网页前端留出渲染和上传的缓冲时间（根据网速调整）
                await asyncio.sleep(5)

            except Exception as e:
                print(f"   ❌ 一键上传过程中发生错误: {e}")
        else:
            print(f"   ⚠️ 商品目录中未找到jpg图片: {goods_image_folder}")
    else:
        print(f"   ⚠️ 商品目录不存在: {goods_image_folder}")

    print("🚀 准备发布商品...")
    try:
        publish_btn = page.locator('button.ant-btn-primary').filter(has_text='发布')
        if await publish_btn.count() > 0:
            is_disabled = await publish_btn.get_attribute('disabled')
            if is_disabled:
                print("⚠️ 发布按钮当前为禁用状态，请检查必填项是否已填写")
            else:
                await publish_btn.click()
                print("✅ 已点击发布按钮")
                publish_success = True
                await asyncio.sleep(3)
        else:
            print("⚠️ 未找到发布按钮")
    except Exception as e:
        print(f"❌ 点击发布按钮失败: {e}")

    return publish_success


async def unlist_last_goods(page):
    """下架刚刚发布的商品"""
    print("\n🔻 准备下架刚刚发布的商品...")

    try:
        # 定位下架按钮
        unlist_btn = page.locator('a.operaBtn--Ur1hcVNu').filter(has_text='下架').first
        if await unlist_btn.count() > 0:
            print("📍 执行下架操作")
            await unlist_btn.click()
            await asyncio.sleep(1)

            # 点击确认下架（弹窗第二个按钮）
            confirm_btn = page.locator(".ant-btn-primary").nth(1)
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
                print("✅ 商品下架成功")
            else:
                print("⚠️ 未找到确认按钮")

            await asyncio.sleep(2)
            return True
        else:
            print("⚠️ 未找到下架按钮")
            return False

    except Exception as e:
        print(f"❌ 下架商品失败: {e}")
        return False


def find_page_by_url(context, target_url):
    """在浏览器上下文中查找包含指定 URL 的页面"""
    for page in context.pages:
        if target_url in page.url:
            return page
    return None


async def get_or_create_publish_page(context):
    """获取或创建发布页面"""
    # 首先检查是否有发布成功页面（包含 publish/success?itemId=）
    for page in context.pages:
        if "publish/success?itemId=" in page.url:
            print("🎉 找到发布成功页面，点击'再发一件'...")
            try:
                another_btn = page.locator('button.btnCommon--osVweuJI.btnPrimary--qbzKZHtf').filter(
                    has_text='再发一件')
                await another_btn.click()
                time.sleep(5)
                return page
            except Exception as e:
                print(f"⚠️ 点击'再发一件'失败: {e}")

    # 然后检查是否有普通发布页面
    publish_page = find_page_by_url(context, "#/seller-item/publish")
    if publish_page:
        print("🔄 找到已打开的发布页面，刷新页面...")
        await publish_page.reload(wait_until="load")
        await publish_page.goto(PUBLISH_URL, wait_until="load")
        time.sleep(3)
        return publish_page

    # 最后创建新页面
    print("🌐 未找到发布页面，创建新页面...")
    new_page = await context.new_page()
    await new_page.goto(PUBLISH_URL, wait_until="load")
    time.sleep(5)
    return new_page


async def get_or_create_goods_manage_page(context):
    """获取或创建商品管理页面"""
    goods_manage_page = find_page_by_url(context, GOODS_MANAGE_URL)
    if goods_manage_page:
        print("🔄 找到已打开的商品管理页面，刷新页面...")
        await goods_manage_page.reload(wait_until="load")
        await asyncio.sleep(3)
        return goods_manage_page
    else:
        print("🌐 未找到商品管理页面，创建新页面...")
        new_page = await context.new_page()
        await new_page.goto(GOODS_MANAGE_URL, wait_until="load")
        await asyncio.sleep(5)
        return new_page


async def run_shelve_and_unlist(goods_id, goods_data):
    """执行上架和下架流程"""
    cookie_path_upload = r"C:\Users\31193\PycharmProjects\playwright__e-commerce\login\cookie\alibaba_cookie\goofish_pro_cookies.json"
    
    print("\n🔗 检查浏览器状态...")
    if not ensure_chrome_running():
        return False, False

    async with async_playwright() as p:
        print("\n🔗 连接浏览器...")
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 无法连接到浏览器: {e}")
            return False, False

        context = browser.contexts[0]

        print(f"\n" + "=" * 60)
        print(f"开始处理商品: {goods_id}")
        print("=" * 60)

        publish_success = True
        unlist_success = False

        publish_page = await get_or_create_publish_page(context)
        await asyncio.sleep(1)
        publish_success = await shelve_single_goods(publish_page, goods_id, goods_data)

        if publish_success:
            print("\n✅ 上架操作成功")
            goods_manage_page = await get_or_create_goods_manage_page(context)
            unlist_success = await unlist_last_goods(goods_manage_page)
        else:
            print("\n❌ 上架操作失败，跳过下架步骤")

        return publish_success, unlist_success


async def main(target_id):
    integrator = GoofishIntegrator()
    print("=" * 60)
    print(f"🛒 开始采集商品: {target_id}")
    print("=" * 60)

    goods_data = await integrator.crawl_single_item(target_id)
    # ===================== 【关键】所有采集完成 → 统一下载 =====================
    print("\n🚀 开始下载所有图片...")

    # 下载商品图
    if goods_data["image_urls"]:
        integrator.download_images(goods_data["item_id"], goods_data["image_urls"])

    # 下载规格图
    if goods_data["spec_image_list"]:
        integrator.download_spec_images(goods_data["item_id"], goods_data["spec_image_list"])

    print(f"\n📊 采集结果:")
    print(f"   商品ID: {goods_data['item_id']}")
    print(f"   价格: {goods_data['price']}")
    print(f"   描述长度: {len(goods_data.get('description', ''))}")
    print(f"   主图数量: {len(goods_data.get('image_urls', []))}")
    print(f"   规格数量: {len(goods_data.get('specs', []))}")

    if goods_data.get('specs') and len(goods_data['specs']) > 0:
        print(f"\n🚀 开始执行上架和下架流程...")
        publish_success, unlist_success = await run_shelve_and_unlist(
            target_id,
            goods_data
        )

        if publish_success and unlist_success:
            print(f"\n✅✅ 商品 {target_id} 上下架流程全部完成")
        else:
            print(f"\n⚠️ 流程未完全成功 (上架:{publish_success}, 下架:{unlist_success})")
    else:
        print(f"\n⚠️ 该商品没有有效规格，跳过上下架流程")


if __name__ == "__main__":
    target_item_id = "1044460638663"
    asyncio.run(main(target_item_id))