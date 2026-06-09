"""Apply anti-detection patches to Playwright contexts and pages.

Reddit (and Cloudflare-fronted sites in general) hard-block headless Chromium
based on a stack of fingerprints: navigator.webdriver=true, missing plugins,
mismatched WebGL vendor, "HeadlessChrome" in the User-Agent, etc.
`tf-playwright-stealth` patches the most-fingerprinted of these. We layer a
hand-rolled UA override on top because the stealth package doesn't change UA.

Designed to be safe to import even if `tf-playwright-stealth` isn't installed:
the module degrades to a no-op with a warning so unit-tests that import the
runtime don't fail purely from a missing optional dep.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Real Chrome 120 UA (matches a current desktop release; matches what the
# Decodo proxy IP pool would naturally see from non-bot residential users).
REAL_CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_STEALTH_FN: Any = None
_STEALTH_IMPORT_ATTEMPTED = False


def _get_stealth_fn():
    """Return a callable(page) that applies stealth patches in-place, or None
    if the package isn't installed. Handles API drift across stealth versions:
    1.x exposes `stealth_sync`, newer versions expose a `Stealth` class."""
    global _STEALTH_FN, _STEALTH_IMPORT_ATTEMPTED
    if _STEALTH_IMPORT_ATTEMPTED:
        return _STEALTH_FN
    _STEALTH_IMPORT_ATTEMPTED = True
    try:
        import playwright_stealth as ps  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Stealth: playwright_stealth not installed (%s) — Reddit may block headless Chromium.",
            exc,
        )
        return None

    if hasattr(ps, "Stealth"):
        instance = ps.Stealth()
        _STEALTH_FN = instance.apply_stealth_sync
        logger.info("Stealth: using Stealth().apply_stealth_sync")
    elif hasattr(ps, "stealth_sync"):
        _STEALTH_FN = ps.stealth_sync
        logger.info("Stealth: using stealth_sync")
    else:
        logger.warning("Stealth: playwright_stealth has neither Stealth nor stealth_sync")
        _STEALTH_FN = None
    return _STEALTH_FN


def harden_context(context) -> None:
    """Apply stealth + UA override to every page in this persistent context.

    Hooks the context's `page` event so brand-new tabs are also patched.
    Idempotent — safe to call once during bootstrap.
    """
    # Patchright applies its own runtime patches at the BrowserContext layer
    # (navigator.webdriver, plugins, console.debug, WebGL, runtime, etc.).
    # Stacking tf-playwright-stealth's init scripts on top causes detectable
    # double-patches (stealth_sync's signatures are themselves fingerprinted).
    # We therefore do NOT call stealth_sync when patchright is active, only
    # the UA-consistency override.
    using_patchright = False
    try:
        # If account_runtime imported context from patchright, the context's
        # module path will contain 'patchright'.
        if "patchright" in type(context).__module__:
            using_patchright = True
    except Exception:  # noqa: BLE001
        pass

    stealth_fn = None if using_patchright else _get_stealth_fn()
    if using_patchright:
        logger.info("Stealth: patchright detected — relying on its built-in patches (skipping stealth_sync)")

    def _harden_page(page) -> None:
        # 1. UA: keep HTTP UA aligned with navigator.userAgent.
        try:
            page.set_extra_http_headers({"User-Agent": REAL_CHROME_UA})
        except Exception:  # noqa: BLE001
            logger.exception("Stealth: failed to set UA headers")

        # 2. (only when NOT on patchright) playwright_stealth init scripts.
        if stealth_fn is not None:
            try:
                stealth_fn(page)
            except Exception:  # noqa: BLE001
                logger.exception("Stealth: stealth call failed")

    # Existing pages (the first one new_page() created in bootstrap).
    for page in context.pages:
        _harden_page(page)

    # All future pages from this context.
    context.on("page", _harden_page)
