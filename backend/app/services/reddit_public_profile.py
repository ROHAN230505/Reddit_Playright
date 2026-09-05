"""Logged-out public Reddit profile fetch via a real Chromium.

`requests` and even Apify-as-HTTP-proxy get Reddit's 403 Blocked wall.
Opening https://www.reddit.com/user/{username}/ in patchright (same stack
as the GLP scraper) is what Dolphin sees. Used for every Reddit account,
including ones added later.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Callable
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

BAN_PHRASES = (
    "this account has been banned",
    "this user has been banned",
    "this account has been suspended",
    "this user has been suspended",
    "account has been permanently suspended",
    "has been permanently banned",
    "user has been banned",
    "account has been banned",
)

GONE_PHRASES = (
    "sorry, nobody on reddit goes by that name",
    "nobody on reddit goes by that name",
    "page not found",
)

BrowserFetch = Callable[[str, str | None], tuple[str, str] | None]


def classify_public_profile_html(username: str, html: str, title: str = "") -> tuple[str, str]:
    """Return (state, detail) from a logged-out profile page."""
    low = (html or "").lower()
    title_low = (title or "").lower()
    uname = (username or "").lower().strip()

    for phrase in BAN_PHRASES:
        if phrase in low:
            return "banned", f"Public profile: {phrase}"
    for phrase in GONE_PHRASES:
        if phrase in low:
            return "missing", f"Public profile: {phrase}"
    if "blocked" in title_low or "whoa there, pardner" in low:
        return "blocked", "Public profile: Reddit returned a Blocked interstitial"
    if uname and (f"u/{uname}" in low or f"overview for {uname}" in low or f"{uname} (u/{uname})" in title_low):
        return "ok", "Public profile page loaded in browser"
    if uname and uname in title_low and "reddit" in title_low:
        return "ok", f"Public profile title {title!r}"
    return "blocked", f"Public profile browser title={title!r}"


def _proxy_to_playwright_dict(proxy_url: str) -> dict:
    parsed = urlparse(proxy_url)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    out: dict = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def _sync_playwright():
    try:
        from patchright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except Exception:  # noqa: BLE001
        from playwright.sync_api import sync_playwright
        return sync_playwright


def _ensure_display() -> subprocess.Popen | None:
    """Start a throwaway Xvfb if this process has no DISPLAY (API container)."""
    if os.environ.get("DISPLAY"):
        return None
    try:
        proc = subprocess.Popen(
            ["Xvfb", ":94", "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    os.environ["DISPLAY"] = ":94"
    for _ in range(10):
        if os.path.exists("/tmp/.X11-unix/X94"):
            break
        time.sleep(0.2)
    return proc


def fetch_public_profile_browser(username: str, proxy_url: str | None) -> tuple[str, str] | None:
    """Open /user/{username}/ logged-out. None if Chromium cannot start."""
    import tempfile

    safe = quote(username, safe="")
    urls = (
        f"https://www.reddit.com/user/{safe}/",
        f"https://old.reddit.com/user/{safe}/",
    )
    xvfb = None
    user_data_dir = tempfile.mkdtemp(prefix="reddit-health-")
    try:
        xvfb = _ensure_display()
        sync_playwright = _sync_playwright()
        headless = not bool(os.environ.get("DISPLAY"))
        launch_args: dict = {
            "user_data_dir": user_data_dir,
            "headless": headless,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1366, "height": 900},
            "locale": "en-US",
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        if proxy_url:
            launch_args["proxy"] = _proxy_to_playwright_dict(proxy_url)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(**launch_args)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                last: tuple[str, str] | None = None
                for url in urls:
                    try:
                        page.goto(url, wait_until="commit", timeout=25_000)
                    except Exception as exc:  # noqa: BLE001
                        logger.info("goto %s failed (%s); reading page anyway", url, exc)
                    try:
                        page.wait_for_timeout(2000)
                        html = page.content()
                        title = page.title()
                    except Exception as exc:  # noqa: BLE001
                        last = ("blocked", f"Browser navigation failed: {exc}")
                        continue
                    state, detail = classify_public_profile_html(username, html, title)
                    last = (state, detail)
                    if state in {"ok", "banned", "missing"}:
                        logger.info(
                            "browser public profile u/%s → %s (%s)",
                            username,
                            state,
                            page.url,
                        )
                        return last
                return last
            finally:
                context.close()
    except Exception:
        logger.exception("browser public profile failed for u/%s", username)
        return None
    finally:
        if xvfb is not None:
            xvfb.kill()
            if os.environ.get("DISPLAY") == ":94":
                os.environ.pop("DISPLAY", None)
        shutil.rmtree(user_data_dir, ignore_errors=True)
