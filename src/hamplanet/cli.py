"""CLI entry point for hamplanet."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from hamplanet.auth import get_authed_context
from hamplanet.scrape import collect_short_urls, collect_video_urls
from hamplanet.store import ActionStore
from hamplanet.vote import VoteResult, downvote, downvote_short

DEFAULT_STORAGE_PATH = Path("storage_state.json")
DEFAULT_DB_PATH = Path("hamplanet.db")
DEFAULT_CONFIG_PATH = Path("channels.json")


def _site_channel(channel_url: str) -> tuple[str, str | None]:
    parsed = urlparse(channel_url)
    host = parsed.netloc.removeprefix("www.")
    site = host.split(".")[0]
    parts = [p for p in parsed.path.split("/") if p]
    channel = parts[-1] if len(parts) >= 2 else None
    return site, channel


def _load_channels(config_path: Path) -> list[str]:
    if not config_path.exists():
        raise SystemExit(
            f"ERROR: config file not found: {config_path}\n"
            f'Create one with: {{"channels": ["https://rumble.com/c/<name>"]}}'
        )
    data = json.loads(config_path.read_text())
    channels = data.get("channels") or []
    if not channels:
        raise SystemExit(f"ERROR: no channels listed in {config_path}")
    return channels


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hamplanet",
        description="Downvote every video and short on a Rumble channel.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to channels config JSON (default: ./channels.json).",
    )
    parser.add_argument(
        "--mode",
        choices=("videos", "shorts", "both"),
        default="both",
        help=(
            "Which content type(s) to process per channel "
            "(default: both — videos pass then shorts pass)."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually click. Without this flag, the run is a dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process at most N items per pass per channel "
            "(0 means scrape-only, no per-item visits)."
        ),
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument(
        "--min-delay",
        type=float,
        default=4.0,
        help="Lower bound of randomized between-item delay in seconds (default: 4.0).",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=6.0,
        help="Upper bound of randomized between-item delay in seconds (default: 6.0).",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Force a fresh login even if storage_state.json exists.",
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=DEFAULT_STORAGE_PATH,
        help="Path to the Playwright storage_state JSON (default: ./storage_state.json).",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Skip authentication. Useful for dry-runs against the public site.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite state DB (default: ./hamplanet.db).",
    )
    parser.add_argument(
        "--ignore-state",
        action="store_true",
        help="Don't skip URLs that are already recorded as acted-on.",
    )
    return parser.parse_args(argv)


async def _run_pass(
    *,
    label: str,
    urls: list[str],
    page: Page,
    store: ActionStore,
    site: str,
    channel: str | None,
    downvoter: Callable[..., Awaitable[VoteResult]],
    args: argparse.Namespace,
    tally: Counter[VoteResult],
) -> None:
    print(f"  {label}: Discovered {len(urls)}")

    if args.limit == 0:
        for url in urls:
            print(url)
        return

    acted = set() if args.ignore_state else store.acted_urls()
    if acted:
        before = len(urls)
        urls = [u for u in urls if u not in acted]
        print(f"  {label}: Skipping {before - len(urls)} already-acted ({len(urls)} remaining)")

    targets = urls if args.limit is None else urls[: args.limit]
    mode_label = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"  {label}: Mode: {mode_label}  Targets: {len(targets)}")

    for i, url in enumerate(targets, 1):
        try:
            result = await downvoter(page, url, execute=args.execute)
            if result == VoteResult.NOT_FOUND:
                # The vote button occasionally fails to render on the first load.
                # A short pause + re-navigation (the downvoter re-goes-to the URL)
                # usually clears it.
                backoff = 3.0
                print(
                    f"  [{i:>3}/{len(targets)}] NOT_FOUND (button may not have rendered); "
                    f"backing off {backoff:.1f}s and retrying"
                )
                await asyncio.sleep(backoff)
                result = await downvoter(page, url, execute=args.execute)
            if result == VoteResult.AUTH_REQUIRED:
                # Often this is actually Rumble's vote rate limit masquerading
                # as the login modal — back off and try once more before
                # accepting the result.
                backoff = max(args.max_delay * 4, 15.0)
                print(
                    f"  [{i:>3}/{len(targets)}] AUTH_REQUIRED (possible rate limit); "
                    f"backing off {backoff:.1f}s and retrying"
                )
                await asyncio.sleep(backoff)
                result = await downvoter(page, url, execute=args.execute)
        except Exception as exc:
            print(f"  [{i:>3}/{len(targets)}] ERROR  {url} :: {exc!r}")
            tally[VoteResult.NOT_FOUND] += 1
            continue

        tally[result] += 1
        print(f"  [{i:>3}/{len(targets)}] {result.value:<14} {url}")

        if result in (VoteResult.CLICKED, VoteResult.ALREADY_DOWN):
            store.record(
                url=url,
                site=site,
                channel=channel,
                action="downvote",
                result=result.value,
            )

        if i < len(targets) and args.max_delay > 0:
            pause = random.uniform(args.min_delay, args.max_delay)
            print(f"          sleeping {pause:.2f}s")
            await asyncio.sleep(pause)


async def run(args: argparse.Namespace) -> int:
    load_dotenv()

    channels = _load_channels(args.config)
    print(f"Loaded {len(channels)} channel(s) from {args.config}")
    print(f"Mode: {args.mode}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)

        if args.no_auth:
            print("Auth: skipped (--no-auth)")
            context = await browser.new_context()
        else:
            username = os.environ.get("RUMBLE_USERNAME")
            password = os.environ.get("RUMBLE_PASSWORD")
            if not username or not password:
                print(
                    "ERROR: RUMBLE_USERNAME and RUMBLE_PASSWORD must be set in .env "
                    "(or pass --no-auth for an unauthenticated dry-run).",
                    file=sys.stderr,
                )
                await browser.close()
                return 2
            print(f"Auth: logging in as {username}")
            context = await get_authed_context(
                browser,
                username=username,
                password=password,
                storage_path=args.storage,
                force_login=args.login,
            )
            print(f"Auth: session ready (storage: {args.storage})")

        page = await context.new_page()
        store = ActionStore(args.db)
        tally: Counter[VoteResult] = Counter()

        try:
            for ch_idx, channel_url in enumerate(channels, 1):
                site, channel = _site_channel(channel_url)
                print(f"\n[Channel {ch_idx}/{len(channels)}] {channel_url}")

                if args.mode in ("videos", "both"):
                    video_urls = await collect_video_urls(page, channel_url)
                    await _run_pass(
                        label="Videos",
                        urls=video_urls,
                        page=page,
                        store=store,
                        site=site,
                        channel=channel,
                        downvoter=downvote,
                        args=args,
                        tally=tally,
                    )

                if args.mode in ("shorts", "both"):
                    short_urls = await collect_short_urls(page, channel_url)
                    await _run_pass(
                        label="Shorts",
                        urls=short_urls,
                        page=page,
                        store=store,
                        site=site,
                        channel=channel,
                        downvoter=downvote_short,
                        args=args,
                        tally=tally,
                    )
        finally:
            store.close()

        await browser.close()

    print("\nSummary:")
    for result, count in sorted(tally.items(), key=lambda kv: kv[0].value):
        print(f"  {result.value:<14} {count}")

    bad = tally[VoteResult.NOT_FOUND] + tally[VoteResult.AUTH_REQUIRED]
    return 1 if bad else 0


def main() -> None:
    args = parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
