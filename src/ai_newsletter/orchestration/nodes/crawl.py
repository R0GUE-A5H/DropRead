import asyncio
import logging
import random
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse

import curl_cffi
import trafilatura
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status
from src.ai_newsletter.utils.ssrf import is_safe_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 3
PAGE_TIMEOUT_MS = 25000

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]
SNIPPET_ONLY_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
}

_domain_stats: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "failures": 0})


def record_domain_result(domain: str, failed: bool) -> None:
    _domain_stats[domain]["attempts"] += 1
    if failed:
        _domain_stats[domain]["failures"] += 1


def should_skip_fast_fetch(domain: str) -> bool:
    """Auto-learned: skip fast fetch if domain has 100% failure rate after 2+ attempts."""
    stats = _domain_stats.get(domain)
    if not stats or stats["attempts"] < 2:
        return False
    return (stats["failures"] / stats["attempts"]) >= 1.0


def should_degrade_to_snippet(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(d in domain for d in SNIPPET_ONLY_DOMAINS) or url.lower().endswith(
        (".pdf", ".doc", ".docx")
    )


def is_waf_challenge(html: str) -> bool:
    """Strict WAF detection. Only matches real challenge pages, not article content."""
    if not html:
        return False
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
    title = title_match.group(1).strip().lower() if title_match else ""
    waf_titles = [
        "just a moment",
        "access denied",
        "verify you are human",
        "captcha",
        "cloudflare",
        "security check",
        "ddos protection",
    ]
    if any(w in title for w in waf_titles):
        return True

    head_match = re.search(r"<head[^>]*>(.*?)</head>", html, re.I | re.DOTALL)
    head = head_match.group(1) if head_match else ""
    waf_head = [
        r"challenge-platform",
        r"cf-chl",
        r"turnstile",
        r"hcaptcha",
        r"ray id",
        r"cf-ray",
        r"imperva",
        r"perimeterx",
        r"datadome",
    ]
    if any(re.search(p, head, re.I) for p in waf_head):
        return True

    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.I | re.DOTALL)
    body = body_match.group(1) if body_match else ""
    waf_body = [
        r'<div[^>]*id=["\']cf-challenge',
        r'<form[^>]*action=["\'].*challenge.*["\']',
        r'data-sitekey=["\']',
        r"cf-challenge-form",
        r"turnstile-container",
    ]
    return any(re.search(p, body, re.I) for p in waf_body)


def is_valid_extraction(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, result["error"]

    content = result.get("content", "")
    html = result.get("raw_html", "")

    if not content or len(content.strip()) < 150:
        return False, "extracted_content_too_short"
    if len(content.split()) < 30:
        return False, "word_count_below_threshold"
    if is_waf_challenge(html):
        return False, "waf_challenge_detected"

    return True, "ok"


async def fast_fetch(url: str, timeout: float = 25.0) -> dict:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    try:
        async with curl_cffi.AsyncSession(impersonate="chrome124") as session:
            resp = await session.get(
                url, headers=headers, timeout=timeout, max_redirects=3
            )
        if resp.status_code != 200:
            return {"url": url, "error": f"HTTP_{resp.status_code}", "raw_html": ""}
        html = resp.text
    except Exception as e:
        return {"url": url, "error": str(e).split("\n")[0], "raw_html": ""}

    extracted = trafilatura.bare_extraction(
        html,
        include_comments=False,
        include_tables=True,
        with_metadata=True,
        as_dict=True,
    )
    content = extracted.get("text", "") if extracted else ""
    return {
        "url": url,
        "title": extracted.get("title") if extracted else None,
        "content": content,
        "raw_html": html,
    }


async def browser_fallback(url: str) -> dict:
    extra_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    if sys.platform != "win32":
        extra_args.extend(
            ["--single-process", "--disable-blink-features=AutomationControlled"]
        )

    browser_config = BrowserConfig(
        enable_stealth=True,
        headless=True,
        extra_args=extra_args,
        user_agent=random.choice(USER_AGENTS),
    )
    run_config = CrawlerRunConfig(
        word_count_threshold=10,
        max_retries=1,
        magic=True,
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
        page_timeout=PAGE_TIMEOUT_MS,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            res = await crawler.arun(url=url, config=run_config)
            if not res or not res.success:
                return {"url": url, "error": f"browser_failed: {res.error_message}"}
            clean = res.markdown or ""
            return {
                "url": url,
                "title": res.metadata.get("title") if res.metadata else None,
                "content": clean,
            }
    except Exception as e:
        return {"url": url, "error": f"browser_exception: {str(e)[:100]}"}


async def crawl_one(url: str, snippet: str = "") -> dict:
    if should_degrade_to_snippet(url):
        if snippet and len(snippet.strip()) > 40:
            return {
                "url": url,
                "title": None,
                "content": snippet,
                "source_type": "snippet",
            }
        return {"url": url, "error": "skipped_non_article"}

    domain = urlparse(url).netloc.lower()

    if not should_skip_fast_fetch(domain):
        result = await fast_fetch(url)
        valid, reason = is_valid_extraction(result)
        record_domain_result(domain, failed=not valid)

        if valid:
            result.pop("raw_html", None)
            return result

        logger.info(f"Fast path failed for {url} | reason: {reason}")
    else:
        logger.info(f"Skipping fast fetch for {domain} — learned high failure rate")

    fb = await browser_fallback(url)
    if "error" not in fb and len(fb.get("content", "").strip()) > 100:
        return fb

    if snippet and len(snippet.strip()) > 40:
        logger.info(f"Using snippet fallback for {url}")
        return {"url": url, "title": None, "content": snippet, "source_type": "snippet"}

    return {"url": url, "error": "all_paths_failed"}


async def web_crawl(
    urls: list[str], snippets: dict[str, str] | None = None
) -> list[dict]:
    snippets = snippets or {}
    safe_urls = [u for u in urls if is_safe_url(u)]
    if len(safe_urls) < len(urls):
        logger.warning(f"Blocked {len(urls) - len(safe_urls)} unsafe URLs")
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def bounded_crawl(u: str):
        async with semaphore:
            return await crawl_one(u, snippets.get(u, ""))

    results = await asyncio.gather(
        *(bounded_crawl(u) for u in safe_urls), return_exceptions=True
    )
    return [r for r in results if not isinstance(r, Exception)]


def run_crawler_in_thread(
    urls: list[str], snippets: dict[str, str] | None = None
) -> list[dict]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(web_crawl(urls, snippets))


async def node_web_crawl(state: GraphState) -> dict:
    urls = list(dict.fromkeys(state.get("search_links", [])))
    snippets = state.get("search_snippets", {})
    logger.info(f"Starting crawl for {len(urls)} URLs")
    logger.info(f"URLs: {urls}")

    if not urls:
        await update_status(state, "running", "No URLs to crawl")
        return {"state_result_page": {}}

    await update_status(state, "running", "Crawling sources...")

    try:
        result_pages = await asyncio.wait_for(
            asyncio.to_thread(run_crawler_in_thread, urls, snippets), timeout=120
        )
    except TimeoutError:
        logger.warning("Crawl timed out after 120s")
        result_pages = []

    new_pages = {}
    logger.info(f"Crawl results: {len(result_pages)} raw results")

    for page in result_pages:
        if isinstance(page, Exception) or "error" in page:
            if isinstance(page, Exception):
                logger.warning(f"Crawl exception: {page}")
            else:
                logger.debug(f"Skipped {page.get('url')}: {page.get('error')}")
            continue
        content = page.get("content", "").strip()
        if len(content) > 50:
            new_pages[page["url"]] = {
                "title": page.get("title"),
                "content": content,
                "source_type": page.get("source_type", "full"),
            }

    logger.info(f"Crawl complete: {len(new_pages)} valid pages")
    return {"state_result_page": new_pages}
