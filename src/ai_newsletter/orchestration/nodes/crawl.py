import asyncio
import logging
import sys

import aiohttp
import trafilatura
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_CONCURRENCY = 1


async def web_crawl(urls: list[str]) -> list[dict]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    extra_args = []

    if sys.platform != "win32":
        extra_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--single-process",
        ]

    browser_config = BrowserConfig(
        enable_stealth=True,
        headless=sys.platform == "win32",
        extra_args=extra_args,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    )
    run_config = CrawlerRunConfig(
        word_count_threshold=10,
        max_retries=2,
        magic=True,
        fallback_fetch_function=simple_fetch_fallback,
        wait_until="load",
        exclude_external_links=True,
        remove_overlay_elements=True,
        process_iframes=False,
        cache_mode=CacheMode.BYPASS,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=None,
            options={
                "ignore_images": True,
                "ignore_links": False,
                "body_width": 0,
                "skip_internal_links": True,
            },
        ),
        page_timeout=15000,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:

        async def crawl_one(url: str):
            if url.lower().endswith(".pdf"):
                return {
                    "url": url,
                    "error": "Skipping PDF: Standard crawler cannot parse binary PDFs.",
                }
            async with semaphore:
                try:
                    res = await crawler.arun(url=url, config=run_config)

                    if res and res.success:
                        title = None
                        clean_content = None

                        if res.html:
                            extracted = trafilatura.bare_extraction(
                                res.html,
                                include_comments=False,
                                include_tables=True,
                                with_metadata=True,
                                as_dict=True,
                            )
                            if extracted:
                                title = extracted.get("title")
                                clean_content = extracted.get("text")

                        if not clean_content:
                            clean_content = res.markdown

                        return {
                            "url": url,
                            "title": title,
                            "content": clean_content,
                        }
                    else:
                        return {
                            "url": url,
                            "error": f"Crawl failed: {res.error_message}",
                        }
                except Exception as e:
                    return {"url": url, "error": str(e)}

        tasks = [crawl_one(url) for url in urls]
        return await asyncio.gather(*tasks)


async def simple_fetch_fallback(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return await resp.text()
            return ""


# 2. Create the synchronous wrapper that enforces the Windows policy
def run_crawler_in_thread(urls: list[str]) -> list[dict]:
    """
    Runs the crawler in a dedicated thread with a Proactor loop.
    This prevents Uvicorn's Selector loop from crashing Playwright on Windows.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # asyncio.run() creates a brand new event loop for this thread,
    # runs the coroutine, and then cleanly closes the loop.
    return asyncio.run(web_crawl(urls))


# 3. Call the thread runner using asyncio.to_thread in your LangGraph node
async def node_web_crawl(state: GraphState) -> GraphState:
    logger.info(f"Starting crawl for {len(state['search_links'])} URLs")
    logger.info(f"URLs: {state['search_links']}")
    try:
        result_pages = await asyncio.wait_for(
            asyncio.to_thread(run_crawler_in_thread, state["search_links"]), timeout=120
        )
    except TimeoutError:
        logger.warning("Crawl timed out after 120s")
        result_pages = []

    await update_status(state, "running", "Searching Internet...")
    new_pages = {}
    logger.info(f"Crawl results: {len(result_pages)} pages")
    for page in result_pages:
        logger.info(
            f"URL: {page.get('url')} | success: {'content' in page} | error: {page.get('error', '')[:100]}"
        )
        if "content" in page and len(page["content"].strip()) > 50:
            new_pages[page["url"]] = {
                "title": page.get("title"),
                "content": page["content"],
            }

    return {"state_result_page": new_pages}
