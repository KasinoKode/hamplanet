"""Click the downvote button on a single Rumble video or short."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DOWNVOTE_SELECTOR = "button.rumbles-vote-pill-down"
DOWNVOTE_SHORT_SELECTOR = 'button[data-testid="vote-down"]'


class VoteResult(StrEnum):
    CLICKED = "CLICKED"
    WOULD_CLICK = "WOULD_CLICK"
    ALREADY_DOWN = "ALREADY_DOWN"
    NOT_FOUND = "NOT_FOUND"
    AUTH_REQUIRED = "AUTH_REQUIRED"


async def downvote(page: Page, video_url: str, *, execute: bool) -> VoteResult:
    """Visit ``video_url`` and downvote it.

    When ``execute`` is False, the button is located and inspected but never clicked
    (returns ``WOULD_CLICK`` or ``ALREADY_DOWN``).
    """
    await page.goto(video_url, wait_until="domcontentloaded")

    button = page.locator(DOWNVOTE_SELECTOR).first

    try:
        await button.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        return VoteResult.NOT_FOUND

    if await _is_active(button):
        return VoteResult.ALREADY_DOWN

    if not execute:
        return VoteResult.WOULD_CLICK

    await button.click()

    # Poll up to 3s for the button to flip to active.
    for _ in range(15):
        await asyncio.sleep(0.2)
        if await _is_active(button):
            return VoteResult.CLICKED
        if await _login_modal_visible(page):
            return VoteResult.AUTH_REQUIRED

    return VoteResult.AUTH_REQUIRED


async def downvote_short(page: Page, short_url: str, *, execute: bool) -> VoteResult:
    """Visit ``short_url`` and downvote it.

    Mirrors :func:`downvote` but targets the shorts vote-down button. Active
    state is detected by the inner ``<span data-vote="down">``: that span is
    present once the short has been downvoted (and absent on an unclicked
    short).
    """
    await page.goto(short_url, wait_until="domcontentloaded")

    button = page.locator(DOWNVOTE_SHORT_SELECTOR).first

    try:
        await button.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        return VoteResult.NOT_FOUND

    if await _is_short_active(button):
        return VoteResult.ALREADY_DOWN

    if not execute:
        return VoteResult.WOULD_CLICK

    await button.click()

    for _ in range(15):
        await asyncio.sleep(0.2)
        if await _is_short_active(button):
            return VoteResult.CLICKED
        if await _login_modal_visible(page):
            return VoteResult.AUTH_REQUIRED

    return VoteResult.AUTH_REQUIRED


async def _is_active(button: Locator) -> bool:
    cls = await button.get_attribute("class") or ""
    return "active" in cls.split()


async def _is_short_active(button: Locator) -> bool:
    # The inner <span data-vote="down"> appears once the short has been
    # downvoted. On an unclicked short the data-vote value differs (or the
    # span is absent), so presence of this exact selector means "already down".
    return await button.locator('span[data-vote="down"]').count() > 0


async def _login_modal_visible(page: Page) -> bool:
    # Rumble's login modal title is "Log In"; a visible heading is a reliable signal.
    try:
        return await page.get_by_role("heading", name="Log In").is_visible(timeout=200)
    except PlaywrightTimeoutError:
        return False
