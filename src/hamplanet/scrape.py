"""Walk a Rumble channel's paginated pages and collect every video URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.async_api import Page

VIDEO_HREF_RE = re.compile(r"^/v[\w]+-[^/]*\.html$")


async def collect_video_urls(page: Page, channel_url: str) -> list[str]:
    """Return absolute video URLs for every video on the channel, in page order."""
    parsed = urlparse(channel_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    seen: dict[str, None] = {}

    page_num = 1
    while True:
        url = f"{channel_url}?page={page_num}"
        await page.goto(url, wait_until="domcontentloaded")

        hrefs: list[str] = await page.locator('a[href^="/v"]').evaluate_all(
            "els => els.map(e => e.getAttribute('href'))"
        )

        page_videos = [
            f"{origin}{href.split('?')[0]}"
            for href in hrefs
            if href and VIDEO_HREF_RE.match(href.split("?")[0])
        ]

        new_videos = [v for v in page_videos if v not in seen]
        if not new_videos:
            break

        for v in new_videos:
            seen[v] = None

        page_num += 1

    return list(seen)
