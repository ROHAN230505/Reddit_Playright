"""Live proxy validation. Routes a quick HTTPS GET through the proxy and
returns the egress IP as confirmation. Lightweight enough to run inline
during a POST /proxies request."""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


CHECK_URL = "https://api.ipify.org?format=json"
CHECK_TIMEOUT_SECONDS = 12


def build_proxy_url(
    *,
    scheme: str,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> str:
    auth = ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth = f"{auth}:{quote(password, safe='')}"
        auth = f"{auth}@"
    return f"{scheme}://{auth}{host}:{port}"


def validate_proxy(
    *,
    scheme: str,
    host: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
    timeout: float = CHECK_TIMEOUT_SECONDS,
) -> tuple[bool, str | None, str | None]:
    """Returns (ok, egress_ip, error_message)."""
    url = build_proxy_url(
        scheme=scheme, host=host, port=port, username=username, password=password
    )
    proxies = {"http": url, "https": url}
    try:
        response = requests.get(CHECK_URL, proxies=proxies, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        ip = data.get("ip")
        if not ip:
            return False, None, "Proxy responded but ipify returned no IP."
        return True, ip, None
    except requests.exceptions.ProxyError as exc:
        return False, None, f"Proxy refused connection: {exc}"
    except requests.exceptions.ConnectTimeout:
        return False, None, "Connection through proxy timed out."
    except requests.exceptions.ReadTimeout:
        return False, None, "Read timeout through proxy."
    except requests.exceptions.SSLError as exc:
        return False, None, f"TLS error through proxy: {exc}"
    except requests.RequestException as exc:
        return False, None, f"Request error: {exc}"
    except ValueError as exc:
        return False, None, f"Invalid JSON from check endpoint: {exc}"
