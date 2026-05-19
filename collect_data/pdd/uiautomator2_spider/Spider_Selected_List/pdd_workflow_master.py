import asyncio
from playwright.async_api import async_playwright
import quality_selection_spider as Scraper
import best_select_index as AIAnalyst
import best_select_url as URLUpdater
from base_backup import Base


async def run_integrated_workflow():
    base = Base()
    CHROME_DEBUG_PORT = 9222

    async with async_playwright() as p:
        base.ensure_chrome_running(proxy_ip=None)
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        print("🚀 第一阶段：开始采集榜单原始数据...")
        raw_data = await Scraper.scrape_pdd_rank(page)
        if raw_data:
            await Scraper.save_goods_to_db(raw_data)

        print("🤖 第二阶段：调用大模型筛选优质选品...")
        source_string = AIAnalyst.get_pdd_source_string()

        # 注意：移除了 await，因为 process_ai_selection 是同步函数
        AIAnalyst.process_ai_selection(source_string)

        print("🖱️ 第三阶段：自动化点击获取详情链接...")
        await URLUpdater.process_selected_products(page)

        print("✨ 工作流执行完毕！完美实现业务闭环！")


if __name__ == "__main__":
    asyncio.run(run_integrated_workflow())