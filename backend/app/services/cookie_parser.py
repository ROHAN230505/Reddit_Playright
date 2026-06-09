"""Parse pasted Reddit cookies into a Playwright-compatible format.

Accepts:
  - JSON array exported from "Cookie-Editor" / "EditThisCookie" Chrome extensions.
  - JSON object {"name": "value", ...}.
  - Bare value of `reddit_session` (the most common quick-paste case).
  - "name=value; name=value" string from DevTools "Copy as cookie string".

Output: list[dict] in Playwright's `context.add_cookies()` shape:
  [{"name": "...", "value": "...", "domain": ".reddit.com", "path": "/",
    "secure": True, "httpOnly": True, "sameSite": "None"}, ...]
"""

from __future__ import annotations

import json
import re
from typing import Any


REDDIT_DOMAIN = ".reddit.com"
ESSENTIAL_COOKIES = {"reddit_session", "token_v2", "loid", "edgebucket"}


def _normalize_cookie(raw: dict) -> dict | None:
    name = raw.get("name") or raw.get("Name")
    value = raw.get("value") or raw.get("Value")
    if not name or value is None:
        return None
    domain = raw.get("domain") or raw.get("Domain") or REDDIT_DOMAIN
    if not domain.startswith("."):
        # Cookie-Editor sometimes exports without a leading dot; Playwright
        # requires the domain to start with `.` for cross-subdomain cookies.
        domain = f".{domain.lstrip('.')}"
    out: dict = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": raw.get("path") or raw.get("Path") or "/",
        "secure": bool(raw.get("secure", raw.get("Secure", True))),
        "httpOnly": bool(raw.get("httpOnly", raw.get("HttpOnly", True))),
    }
    same_site = raw.get("sameSite") or raw.get("SameSite") or "None"
    if isinstance(same_site, str):
        ss = same_site.lower().strip()
        if ss in ("strict", "lax", "none"):
            out["sameSite"] = ss.capitalize()
    expires = raw.get("expirationDate") or raw.get("expires") or raw.get("Expires")
    if expires is not None:
        try:
            out["expires"] = float(expires)
        except (TypeError, ValueError):
            pass
    return out


def _parse_cookie_string(raw: str) -> list[dict]:
    """Parse 'a=1; b=2' into Playwright cookies."""
    out: list[dict] = []
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        out.append({
            "name": name,
            "value": value,
            "domain": REDDIT_DOMAIN,
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "None",
        })
    return out


def parse_cookies(raw: str) -> list[dict]:
    """Parse pasted input into Playwright-cookie shape. Raises ValueError on garbage."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("Cookie input is empty.")

    # 1. JSON array (Cookie-Editor export).
    if s.startswith("["):
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Looks like JSON but could not parse: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("JSON must be an array of cookie objects.")
        cookies = [c for raw_c in parsed if isinstance(raw_c, dict) and (c := _normalize_cookie(raw_c))]
        if not cookies:
            raise ValueError("JSON array contained no recognizable cookies.")
        return cookies

    # 2. JSON object {name: value}.
    if s.startswith("{"):
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Looks like JSON but could not parse: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON object expected name→value mapping.")
        out: list[dict] = []
        for name, value in parsed.items():
            if isinstance(value, dict) and ("value" in value or "Value" in value):
                cookie = _normalize_cookie({"name": name, **value})
            else:
                cookie = _normalize_cookie({"name": name, "value": str(value)})
            if cookie:
                out.append(cookie)
        if not out:
            raise ValueError("JSON object contained no recognizable cookies.")
        return out

    # 3. "name=value; name=value" string.
    if "=" in s:
        cookies = _parse_cookie_string(s)
        if cookies:
            return cookies

    # 4. Bare value — assume it's reddit_session.
    if re.fullmatch(r"[A-Za-z0-9_\-:.%+/=]+", s):
        return [{
            "name": "reddit_session",
            "value": s,
            "domain": REDDIT_DOMAIN,
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "None",
        }]

    raise ValueError(
        "Could not interpret input. Paste either the JSON export from "
        "Cookie-Editor, a 'name=value; name=value' string, or just the "
        "reddit_session value."
    )


def has_essential_cookie(cookies: list[dict]) -> bool:
    """True if the parsed cookies include at least one auth-bearing entry."""
    names = {c.get("name") for c in cookies}
    return bool(names & ESSENTIAL_COOKIES)


def serialize_for_db(cookies: list[dict]) -> str:
    """Compact JSON suitable for encryption + storage."""
    return json.dumps(cookies, separators=(",", ":"))


def deserialize_from_db(raw: str) -> list[dict]:
    return json.loads(raw)
