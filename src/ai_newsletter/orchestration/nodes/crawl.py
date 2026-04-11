import asyncio

import trafilatura
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

MAX_CONCURRENCY = 4


async def web_crawl(urls: list[str]) -> list[dict]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    browser_config = BrowserConfig(
        enable_stealth=True,
        headless=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    )
    run_config = CrawlerRunConfig(
        # excluded_tags=["nav", "footer", "aside", "script", "style", "noscript"],
        # css_selector="article, main, .post-content, .article-body, #main-content",
        word_count_threshold=10,
        magic=True,
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
        page_timeout=60000,
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
                            # print(
                            #     f"trafilatura failed for {url}, falling back to markdown"
                            # )
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
        results = await asyncio.gather(*tasks)
        return results


async def node_web_crawl(state: GraphState) -> GraphState:
    # print(f"-------Starting web crawl for {len(state['search_links'])} URLs------")
    result_pages = await web_crawl(state["search_links"])
    await update_status(state, "running", "Searching Internet...")
    new_pages = {}

    for page in result_pages:
        if "content" in page and len(page["content"].strip()) > 50:
            new_pages[page["url"]] = {
                "title": page.get("title"),
                "content": page["content"],
            }
            # print(f"[CRAWLED] {page['url']} | Title: {page.get('title', 'N/A')}")
        # else:
        #     print(f"Error on {page['url']}: {page.get('error')}")

    return {"state_result_page": new_pages}
