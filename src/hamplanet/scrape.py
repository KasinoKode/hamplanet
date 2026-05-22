"""Walk a Rumble channel's paginated pages and collect every video / short URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.async_api import Page

VIDEO_HREF_RE = re.compile(r"^/v[\w]+-[^/]*\.html$")
SHORT_HREF_RE = re.compile(r"^/shorts/v[\w]+$")


async def collect_video_urls(page: Page, channel_url: str) -> list[str]:
    """Return absolute video URLs for every video on the channel, in page order."""
    return await _paginated_collect(
        page,
        base_url=channel_url,
        anchor_selector='a[href^="/v"]',
        href_re=VIDEO_HREF_RE,
    )


async def collect_short_urls(page: Page, channel_url: str) -> list[str]:
    """Return absolute short URLs for every short on the channel, in page order."""
    return await _paginated_collect(
        page,
        base_url=f"{channel_url.rstrip('/')}/shorts",
        anchor_selector='a[href^="/shorts/"]',
        href_re=SHORT_HREF_RE,
    )


async def _paginated_collect(
    page: Page,
    *,
    base_url: str,
    anchor_selector: str,
    href_re: re.Pattern[str],
) -> list[str]:
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    seen: dict[str, None] = {}

    page_num = 1
    while True:
        url = f"{base_url}?page={page_num}"
        await page.goto(url, wait_until="domcontentloaded")

        hrefs: list[str] = await page.locator(anchor_selector).evaluate_all(
            "els => els.map(e => e.getAttribute('href'))"
        )

        page_items = [
            f"{origin}{href.split('?')[0]}"
            for href in hrefs
            if href and href_re.match(href.split("?")[0])
        ]

        new_items = [v for v in page_items if v not in seen]
        if not new_items:
            break

        for v in new_items:
            seen[v] = None

        page_num += 1

    return list(seen)
