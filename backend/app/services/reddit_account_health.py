"""Reddit account health: public profile is the source of truth.

A banned account can keep a live session for a while. `me.json` 200 and
decryptable cookies are NOT proof the account is allowed to post. The public
profile page (`This account has been banned`) is.

Health values:
  HEALTHY      public profile ok AND session alive
  BANNED       public profile says banned/suspended/gone
  SESSION_DEAD profile ok, cookies present but me.json is not that user
  NO_COOKIES   profile ok, no session cookies stored
  PROXY_DEAD   assigned proxy could not reach Reddit
  UNKNOWN      profile could not be classified and session is not proven alive
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import requests

from app.db.models import RedditAccount
from app.services import crypto
from app.services.cookie_parser import deserialize_from_db
from app.services.proxy_check import build_proxy_url

logger = logging.getLogger(__name__)

HEALTHY = "HEALTHY"
BANNED = "BANNED"
SESSION_DEAD = "SESSION_DEAD"
NO_COOKIES = "NO_COOKIES"
PROXY_DEAD = "PROXY_DEAD"
UNKNOWN = "UNKNOWN"

LIVE_TTL_SECONDS = 20
CHECK_TIMEOUT_SECONDS = 8
MAX_PARALLEL = 4

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
}

# Lowercased phrases from Reddit's public banned/suspended profile pages.
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

BLOCK_PHRASES = (
    "too many requests",
    "request was blocked",
    "access denied",
    "forbidden",
)

HttpGet = Callable[..., Any]


@dataclass(frozen=True)
class HealthResult:
    health: str
    detail: str
    session_alive: bool | None
    profile_banned: bool | None


def _default_get(url: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", None) or DEFAULT_HEADERS
    return requests.get(
        url,
        headers=headers,
        timeout=kwargs.pop("timeout", CHECK_TIMEOUT_SECONDS),
        allow_redirects=True,
        **kwargs,
    )


def _html_matches(text: str, phrases: tuple[str, ...]) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for phrase in phrases:
        if phrase in lowered:
            return phrase
    return None


def _me_user(payload: Any) -> dict:
    if not isinstance(payload, dict) or not payload:
        return {}
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _me_username(payload: Any) -> str | None:
    name = _me_user(payload).get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _me_suspended(payload: Any) -> bool:
    inner = _me_user(payload)
    return bool(inner.get("is_suspended") or inner.get("is_banned"))


def _json_profile_state(payload: Any) -> str | None:
    """Return banned/ok/missing from /user/{name}/about.json, or None if unusable."""
    if not isinstance(payload, dict):
        return None
    if payload.get("error") in (404, "404") or str(payload.get("message", "")).lower() == "not found":
        return "missing"
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(inner, dict):
        return None
    if inner.get("is_suspended") or inner.get("is_banned") or inner.get("is_blocked"):
        return "banned"
    if inner.get("name"):
        return "ok"
    return None


def _fetch(getter: HttpGet, url: str, *, cookies: dict | None, proxy_url: str | None):
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    headers = dict(DEFAULT_HEADERS)
    if "about.json" in url:
        headers["Accept"] = "application/json"
    timeout = CHECK_TIMEOUT_SECONDS
    if proxy_url and "proxy.apify.com" in proxy_url:
        timeout = 15
    return getter(
        url,
        cookies=cookies or None,
        proxies=proxies,
        headers=headers,
        timeout=timeout,
    )


def _classify_profile_response(response: Any) -> tuple[str, str]:
    """Return (state, detail) where state is banned/ok/missing/blocked/error."""
    status = getattr(response, "status_code", None)
    text = getattr(response, "text", "") or ""
    json_payload = None
    try:
        json_payload = response.json()
    except Exception:  # noqa: BLE001
        json_payload = None

    json_state = _json_profile_state(json_payload) if json_payload is not None else None
    ban_phrase = _html_matches(text, BAN_PHRASES)
    gone_phrase = _html_matches(text, GONE_PHRASES)
    block_phrase = _html_matches(text, BLOCK_PHRASES)

    if ban_phrase or json_state == "banned":
        reason = ban_phrase or "profile is_suspended/is_banned"
        return "banned", f"Public profile: {reason}"
    if json_state == "ok" and status and 200 <= int(status) < 400:
        return "ok", "Public profile exists"
    if gone_phrase or json_state == "missing" or status == 404:
        reason = gone_phrase or "profile 404 / not found"
        return "missing", f"Public profile: {reason}"
    if "<title>blocked</title>" in text.lower() or "title>Blocked</title>" in text:
        return "blocked", "Public profile: Reddit returned a Blocked interstitial"
    if status in (401, 403, 429) or block_phrase:
        return "blocked", f"Public profile HTTP {status}" + (f" ({block_phrase})" if block_phrase else "")
    # A 200 HTML shell is not proof the public profile is live. New Reddit
    # and logged-in overviews both contain the word "reddit". Only JSON
    # about.json (unauthenticated) counts as ok.
    return "error", f"Public profile HTTP {status}"


def check_reddit_account(
    *,
    username: str,
    cookie_header: dict[str, str] | None,
    proxy_url: str | None,
    http_get: HttpGet | None = None,
    public_proxy_url: str | None = None,
) -> HealthResult:
    getter = http_get or _default_get
    safe = quote(username, safe="")
    profile_urls = (
        f"https://old.reddit.com/user/{safe}/about.json",
        f"https://www.reddit.com/user/{safe}/about.json",
        f"https://old.reddit.com/user/{safe}/",
        f"https://www.reddit.com/user/{safe}/",
    )
    if public_proxy_url is None:
        try:
            from app.services.apify_service import residential_proxy_url

            public_proxy_url = residential_proxy_url()
        except Exception:  # noqa: BLE001
            public_proxy_url = None

    profile_state = "error"
    profile_detail = "Public profile was not fetched"
    proxy_failed = False
    last_exc: str | None = None

    def _try_urls(use_proxy: str | None, cookies: dict | None = None) -> bool:
        nonlocal profile_state, profile_detail, last_exc
        seen: list[tuple[str, str]] = []
        for url in profile_urls:
            try:
                response = _fetch(getter, url, cookies=cookies, proxy_url=use_proxy)
            except requests.exceptions.ProxyError as exc:
                last_exc = f"Proxy error: {exc}"
                raise
            except requests.RequestException as exc:
                last_exc = str(exc)
                continue
            except Exception as exc:  # noqa: BLE001
                last_exc = str(exc)
                continue
            state, detail = _classify_profile_response(response)
            seen.append((state, detail))
            # Ban is definitive. "ok" is not — about.json may still say
            # is_suspended after a generic HTML 200.
            if state == "banned":
                profile_state, profile_detail = state, detail
                return True
        if not seen:
            return False
        # Prefer a live about.json over a 404 from another host (old.reddit
        # often returns plain "Not Found" while www still has the user).
        for state, detail in seen:
            if state == "ok":
                profile_state, profile_detail = state, detail
                return True
        for state, detail in seen:
            if state == "missing":
                profile_state, profile_detail = state, detail
                return True
        profile_state, profile_detail = seen[-1]
        return False

    try:
        classified = _try_urls(proxy_url)
    except requests.exceptions.ProxyError as exc:
        proxy_failed = True
        last_exc = str(exc)
        classified = False

    if not classified and proxy_url:
        # Ban pages are public — if the assigned proxy is dead, still try
        # a direct fetch so the panel can show BANNED vs PROXY_DEAD.
        try:
            classified = _try_urls(None)
        except Exception as exc:  # noqa: BLE001
            last_exc = str(exc)

    if (
        not classified
        and public_proxy_url
        and public_proxy_url != proxy_url
    ):
        # Account proxies and this VPS get Reddit's logged-out 403 wall.
        # Apify residential is the same network the scraper already uses.
        try:
            classified = _try_urls(public_proxy_url)
            if classified:
                logger.info(
                    "reddit public profile u/%s classified via Apify residential",
                    username,
                )
        except Exception as exc:  # noqa: BLE001
            last_exc = str(exc)

    session_alive: bool | None = None
    session_detail = ""
    me_suspended = False
    if cookie_header:
        me_urls = (
            "https://old.reddit.com/api/me.json",
            "https://www.reddit.com/api/me.json",
        )
        me_proxy = proxy_url if not proxy_failed else None
        me_payload = None
        for url in me_urls:
            try:
                response = _fetch(getter, url, cookies=cookie_header, proxy_url=me_proxy)
            except requests.RequestException as exc:
                session_detail = str(exc)
                continue
            except Exception as exc:  # noqa: BLE001
                session_detail = str(exc)
                continue
            try:
                me_payload = response.json()
            except Exception:  # noqa: BLE001
                me_payload = None
            me_name = _me_username(me_payload)
            if response.status_code == 200 and me_name:
                session_alive = me_name.lower() == username.lower()
                me_suspended = _me_suspended(me_payload)
                if session_alive:
                    session_detail = f"me.json 200 as {me_name}"
                    if me_suspended:
                        session_detail += " is_suspended=true"
                else:
                    session_detail = f"me.json 200 as {me_name}, expected {username}"
                break
            if response.status_code in (401, 403):
                session_alive = False
                session_detail = f"me.json HTTP {response.status_code}"
                break
            if response.status_code == 200 and not me_name:
                session_alive = False
                session_detail = "me.json 200 but logged out"
                break
        if session_alive is None and session_detail:
            session_alive = False

        # Logged-in about.json/overview still look fine after a site-wide
        # ban (the operator screenshot is the logged-OUT public page). Only
        # keep an authed fetch if it actually contains the ban phrase.
        if cookie_header and profile_state != "banned" and session_alive is not False:
            public_state, public_detail = profile_state, profile_detail
            try:
                _try_urls(me_proxy, cookie_header)
            except requests.exceptions.ProxyError:
                profile_state, profile_detail = public_state, public_detail
            except Exception as exc:  # noqa: BLE001
                last_exc = str(exc)
                profile_state, profile_detail = public_state, public_detail
            else:
                if profile_state != "banned":
                    profile_state, profile_detail = public_state, public_detail

    if me_suspended:
        profile_state = "banned"
        profile_detail = "me.json is_suspended=true (session still alive)"

    profile_banned = profile_state in ("banned", "missing")

    if profile_banned:
        extra = f"; {session_detail}" if session_detail else ""
        if session_alive:
            extra = f"; session still alive ({session_detail})" if session_detail else "; session still alive"
        return HealthResult(
            health=BANNED,
            detail=(profile_detail + extra)[:2000],
            session_alive=session_alive,
            profile_banned=True,
        )

    if profile_state != "ok":
        if proxy_failed and profile_state == "error":
            return HealthResult(
                health=PROXY_DEAD,
                detail=(last_exc or profile_detail)[:2000],
                session_alive=session_alive,
                profile_banned=None,
            )
        detail = profile_detail if profile_state != "error" else (last_exc or profile_detail)
        # Logged-out Reddit pages 403 from this VPS even for healthy accounts.
        # A live session + no suspend flag is the usable signal. profile_banned
        # stays None so sticky BANNED cannot clear itself off a bot wall.
        if session_alive is True:
            return HealthResult(
                health=HEALTHY,
                detail=(
                    f"{detail}; session alive. Public profile was blocked so this "
                    "is not a logged-out confirm."
                )[:2000],
                session_alive=True,
                profile_banned=None,
            )
        if cookie_header:
            return HealthResult(
                health=SESSION_DEAD,
                detail=(
                    f"{detail}; {session_detail or 'session not authenticated'}"
                )[:2000],
                session_alive=False,
                profile_banned=None,
            )
        return HealthResult(
            health=UNKNOWN,
            detail=detail[:2000],
            session_alive=session_alive,
            profile_banned=None,
        )

    # Public profile is fine. Session decides whether we can post.
    if not cookie_header:
        return HealthResult(
            health=NO_COOKIES,
            detail="Public profile ok; no session cookies stored",
            session_alive=False,
            profile_banned=False,
        )
    if session_alive is True:
        return HealthResult(
            health=HEALTHY,
            detail=f"Public profile ok; {session_detail or 'session alive'}",
            session_alive=True,
            profile_banned=False,
        )
    return HealthResult(
        health=SESSION_DEAD,
        detail=f"Public profile ok; {session_detail or 'session not authenticated'}",
        session_alive=False,
        profile_banned=False,
    )


def cookies_for_requests(account: RedditAccount) -> dict[str, str] | None:
    if not account.session_cookies_enc:
        return None
    try:
        raw = crypto.decrypt(account.session_cookies_enc)
        cookies = deserialize_from_db(raw)
    except Exception:  # noqa: BLE001
        logger.warning("Could not decrypt cookies for u/%s", account.username)
        return None
    out: dict[str, str] = {}
    for item in cookies or []:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            out[str(name)] = str(value)
    return out or None


def proxy_url_for_account(account: RedditAccount) -> str | None:
    proxy = account.proxy
    if proxy is None:
        return None
    password = None
    if proxy.password_enc:
        try:
            password = crypto.decrypt(proxy.password_enc)
        except Exception:  # noqa: BLE001
            password = None
    return build_proxy_url(
        scheme=proxy.scheme or "http",
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=password,
    )


def apply_health_to_account(account: RedditAccount, result: HealthResult) -> None:
    previous_status = (account.status or "").upper()
    previous_health = (account.reddit_health or "").upper()
    # A site-banned account keeps a live session. Do not unban just because
    # me.json still returns 200. Only a positive public-profile "not banned"
    # (profile_banned is False) may clear it.
    if (
        result.health != BANNED
        and result.profile_banned is not False
        and (previous_status == BANNED or previous_health == BANNED)
    ):
        result = HealthResult(
            health=BANNED,
            detail=(
                "Kept BANNED: session alive is not enough to unban. "
                f"Latest={result.health}. {result.detail}"
            )[:2000],
            session_alive=result.session_alive,
            profile_banned=True,
        )
    account.reddit_health = result.health
    account.reddit_health_detail = result.detail[:2000]
    account.reddit_health_checked_at = datetime.utcnow()
    account.reddit_session_alive = result.session_alive
    if result.health == BANNED:
        account.status = BANNED
        account.is_enabled = False
        account.last_error = result.detail[:2000]


def account_is_postable(account: RedditAccount) -> bool:
    if not account.is_enabled:
        return False
    if (account.status or "").upper() != "ACTIVE":
        return False
    if (account.platform or "reddit") != "reddit":
        return True
    if not account.session_cookies_enc:
        return False
    health = (account.reddit_health or "").upper()
    if health in {BANNED, SESSION_DEAD, PROXY_DEAD}:
        return False
    return True


def refresh_reddit_health(
    db,  # Session
    accounts: list[RedditAccount],
    *,
    min_age_seconds: float = LIVE_TTL_SECONDS,
    force: bool = False,
    http_get: HttpGet | None = None,
) -> int:
    """Check stale Reddit accounts and write health onto the ORM rows.

    Returns the number of accounts actually checked.
    """
    now = datetime.utcnow()
    jobs: list[dict] = []
    for account in accounts:
        if (account.platform or "reddit") != "reddit":
            continue
        checked = account.reddit_health_checked_at
        if (
            not force
            and checked is not None
            and (now - checked).total_seconds() < min_age_seconds
        ):
            continue
        jobs.append(
            {
                "id": account.id,
                "username": account.username,
                "cookie_header": cookies_for_requests(account),
                "proxy_url": proxy_url_for_account(account),
                "had_cookie_blob": bool(account.session_cookies_enc),
            }
        )
    if not jobs:
        return 0

    results: dict[int, HealthResult] = {}
    workers = min(MAX_PARALLEL, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                check_reddit_account,
                username=job["username"],
                cookie_header=job["cookie_header"],
                proxy_url=job["proxy_url"],
                http_get=http_get,
            ): job
            for job in jobs
        }
        for fut in as_completed(futs):
            job = futs[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Health check failed for u/%s", job["username"])
                result = HealthResult(
                    health=UNKNOWN,
                    detail=str(exc)[:2000],
                    session_alive=None,
                    profile_banned=None,
                )
            if (
                result.health == NO_COOKIES
                and job["had_cookie_blob"]
                and job["cookie_header"] is None
            ):
                result = HealthResult(
                    health=SESSION_DEAD,
                    detail="Public profile ok; stored cookies could not be decrypted",
                    session_alive=False,
                    profile_banned=False,
                )
            results[job["id"]] = result

    by_id = {account.id: account for account in accounts}
    for account_id, result in results.items():
        account = by_id.get(account_id)
        if account is None:
            continue
        apply_health_to_account(account, result)
        db.add(account)
        logger.info(
            "reddit health u/%s → %s session_alive=%s (%s)",
            account.username,
            result.health,
            result.session_alive,
            result.detail[:180],
        )
    return len(results)
