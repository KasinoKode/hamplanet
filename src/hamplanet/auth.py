"""Rumble authentication: login form fill + storage_state caching."""

from __future__ import annotations

import contextlib
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

LOGIN_URL = "https://rumble.com/login.php"
HOME_URL = "https://rumble.com/"


async def get_authed_context(
    browser: Browser,
    *,
    username: str,
    password: str,
    storage_path: Path,
    force_login: bool,
) -> BrowserContext:
    """Return a logged-in browser context.

    Tries the cached ``storage_state.json`` first (unless ``force_login``).
    If the cached state is missing or stale, performs a fresh login with the
    supplied credentials and persists the resulting state.
    """
    if not force_login and storage_path.exists():
        context = await browser.new_context(storage_state=str(storage_path))
        page = await context.new_page()
        if await _is_logged_in(page):
            await page.close()
            return context
        await context.close()

    context = await browser.new_context()
    page = await context.new_page()
    await _login_with_credentials(page, username, password)
    if not await _is_logged_in(page):
        await context.close()
        raise RuntimeError("Login submitted but session still appears anonymous")
    await context.storage_state(path=str(storage_path))
    await page.close()
    return context


async def _login_with_credentials(page: Page, username: str, password: str) -> None:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.locator('input[name="username"]').fill(username)
    await page.locator('input[name="password"]').fill(password)
    await page.locator('button[type="submit"]').click()
    # Some flows linger on auth.rumble.com briefly; _is_logged_in is the final arbiter.
    with contextlib.suppress(PlaywrightTimeoutError):
        await page.wait_for_url("https://rumble.com/**", timeout=20_000)


async def _is_logged_in(page: Page) -> bool:
    """Check session by visiting the home page and looking for the Sign In link."""
    await page.goto(HOME_URL, wait_until="domcontentloaded")
    sign_in = page.locator('a:has-text("Sign In")').first
    try:
        return not await sign_in.is_visible(timeout=2_000)
    except PlaywrightTimeoutError:
        return True
