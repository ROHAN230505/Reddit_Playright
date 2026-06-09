"""Per-account Playwright runtime for the multi-account Reddit posting worker.

Each AccountRuntime owns one persistent BrowserContext for exactly one Reddit
account. It is responsible for:
- Bootstrapping (creating user-data-dir, launching the context, logging in).
- Processing one posting job at a time via process_one().
- Sending heartbeats to the backend after every significant state transition.
- Shutting down cleanly when the orchestrator removes or stops it.

AccountRuntime is intentionally single-threaded. The orchestrator in runner.py
calls runtimes sequentially (round-robin), so no locking is needed here.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Callable

from patchright.sync_api import BrowserContext, Playwright

from .client import BackendClient, BackendError
from .config import WorkerConfig
from .chan_poster import ChanBanned, ChanFloodControl, ChanThreadDead
from .chan_poster import post_reply as chan_post_reply
from .glp_login import automated_glp_login, is_logged_in as glp_is_logged_in
from .glp_poster import GlpBanned, GlpFloodControl
from .glp_poster import post_reply as glp_post_reply
from .login import CaptchaEncountered, LoginFailed, automated_login, is_logged_in
from .poster import CaptchaEncountered as PostCaptcha
from .poster import PostingError, post_reply

logger = logging.getLogger(__name__)


class AccountRuntime:
    """Manages the lifecycle of a single Reddit account's browser session."""

    def __init__(
        self,
        playwright: Playwright,
        account: dict,
        config: WorkerConfig,
        client_factory: Callable[[], BackendClient],
    ) -> None:
        self._playwright = playwright
        self.account = account
        self._config = config
        self._client: BackendClient = client_factory()
        self._context: BrowserContext | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def _chan_pass_credentials(self) -> tuple[str | None, str | None]:
        """4chan Pass token/PIN for this account.

        Per-account values on the account record win (keys `chan_pass_token` /
        `chan_pass_pin`); otherwise fall back to the worker-wide env config.
        A Pass is shared (one IP at a time), so the env default is the common
        case and the per-account override is for running distinct Passes.
        """
        token = self.account.get("chan_pass_token") or self._config.chan_pass_token
        pin = self.account.get("chan_pass_pin") or self._config.chan_pass_pin
        return ((token or "").strip() or None, (str(pin) if pin else "").strip() or None)

    def _chan_post_with_pass_retry(self, job: dict, reply_id: int, username: str) -> dict:
        """Post a 4chan reply, re-authing the Pass once if a captcha appears.

        A captcha on a Pass-enabled context means the cookie went stale (expired,
        or the Pass IP binding rotated away from us). We re-auth through this
        context and retry exactly once. If there's no Pass configured, or the
        re-auth itself fails, the original CaptchaEncountered propagates.
        """
        try:
            return chan_post_reply(
                self._context, job, screenshot_dir=self._config.screenshot_dir
            )
        except PostCaptcha:
            token, pin = self._chan_pass_credentials()
            if not (token and pin):
                raise  # no Pass to refresh — let the captcha surface
            from .chan_auth import ChanPassError, ensure_authenticated
            logger.warning(
                "[%s] 4chan captcha on reply_id=%s — re-authing Pass and retrying",
                username, reply_id,
            )
            try:
                ensure_authenticated(self._context, token, pin, force=True)
            except ChanPassError as exc:
                logger.error("[%s] Pass re-auth failed: %s", username, exc)
                raise  # propagate the captcha; account stays usable
            return chan_post_reply(
                self._context, job, screenshot_dir=self._config.screenshot_dir
            )

    def bootstrap(self) -> None:
        """Build user-data-dir, launch the persistent context, and log in if needed.

        Raises LoginFailed or CaptchaEncountered on authentication failure — the
        orchestrator is expected to catch these and skip this account.
        """
        account_id = self.account["id"]
        username = self.account["username"]
        user_data_dir = self.account["user_data_dir"]

        logger.info("[%s] Bootstrapping account id=%s", username, account_id)

        os.makedirs(user_data_dir, exist_ok=True)

        # Per-account profile from the backend (browser fingerprint slot 0..9).
        # If the backend didn't supply one (legacy behaviour), fall back to
        # the original constants so we still produce a consistent fingerprint.
        from .stealth import REAL_CHROME_UA

        profile = self.account.get("profile") or {}
        ua = profile.get("user_agent") or REAL_CHROME_UA
        viewport = {
            "width": int(profile.get("viewport_width") or 1280),
            "height": int(profile.get("viewport_height") or 900),
        }
        locale = profile.get("locale") or "en-US"
        timezone_id = profile.get("timezone_id") or "America/New_York"
        device_scale_factor = float(profile.get("device_scale_factor") or 1.0)
        logger.info(
            "[%s] Profile: viewport=%sx%s tz=%s scale=%s ua-chrome=%s",
            username,
            viewport["width"],
            viewport["height"],
            timezone_id,
            device_scale_factor,
            ua.split("Chrome/")[1].split(".")[0] if "Chrome/" in ua else "?",
        )

        launch_kwargs: dict = {
            "user_data_dir": user_data_dir,
            "headless": self._config.headless,
            "viewport": viewport,
            "user_agent": ua,
            "locale": locale,
            "timezone_id": timezone_id,
            "device_scale_factor": device_scale_factor,
            # NOTE: with patchright we deliberately do NOT pass
            # `--disable-blink-features=AutomationControlled` — patchright
            # applies that itself and external duplication breaks its stealth.
            "args": [
                "--no-default-browser-check",
                "--no-first-run",
            ],
        }
        if self._config.browser_channel:
            launch_kwargs["channel"] = self._config.browser_channel

        proxy = self.account.get("proxy")
        if proxy:
            proxy_server = f"{proxy['scheme']}://{proxy['host']}:{proxy['port']}"
            proxy_kwargs: dict = {"server": proxy_server}
            if proxy.get("username"):
                proxy_kwargs["username"] = proxy["username"]
            if proxy.get("password"):
                proxy_kwargs["password"] = proxy["password"]
            launch_kwargs["proxy"] = proxy_kwargs
            logger.info("[%s] Using proxy %s", username, proxy_server)

        self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)

        # Apply stealth patches BEFORE any page is created so the first page
        # picks them up. harden_context() also hooks future pages.
        from .stealth import harden_context
        harden_context(self._context)

        # If the operator pasted session cookies via the dashboard, inject
        # them BEFORE the is_logged_in check. This lets us skip Reddit's
        # auth-flow (which hard-blocks headless Chromium) entirely.
        pasted_cookies = self.account.get("session_cookies")
        if pasted_cookies:
            try:
                self._context.add_cookies(pasted_cookies)
                logger.info(
                    "[%s] Injected %d pasted session cookie(s)",
                    username,
                    len(pasted_cookies),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[%s] Failed to inject pasted cookies: %s — will fall back to login flow",
                    username,
                    exc,
                )

        platform = (self.account.get("platform") or "reddit").lower()
        # 4chan posts anonymously — no username/password login. If a 4chan Pass
        # is configured we authenticate it here so posts skip the per-post
        # reCAPTCHA. The Pass binds to one IP at a time, so we auth through this
        # (proxied) context, the same path posts go out on.
        if platform == "chan":
            token, pin = self._chan_pass_credentials()
            if token and pin:
                from .chan_auth import ChanPassError, ensure_authenticated
                try:
                    ensure_authenticated(self._context, token, pin)
                    logger.info("[%s] platform=chan — 4chan Pass authenticated", username)
                    self._heartbeat("bootstrap_chan_pass", status="ACTIVE")
                except ChanPassError as exc:
                    # Bad/expired Pass — don't hard-fail the account; posting
                    # will simply hit the captcha and surface CaptchaEncountered.
                    logger.error("[%s] 4chan Pass auth failed: %s", username, exc)
                    self._heartbeat("chan_pass_failed", status="ACTIVE", error=str(exc))
            else:
                logger.info("[%s] platform=chan — no Pass configured (captcha-gated)",
                            username)
                self._heartbeat("bootstrap_no_login", status="ACTIVE")
            return

        login_fn = automated_glp_login if platform == "glp" else automated_login
        check_logged_in = glp_is_logged_in if platform == "glp" else is_logged_in

        page = self._context.new_page()
        try:
            if check_logged_in(page):
                logger.info("[%s] Already logged in (%s) — skipping automated login",
                            username, platform)
                self._heartbeat("bootstrap_already_logged_in", status="ACTIVE")
            else:
                self._heartbeat("bootstrap_login_start", status="VERIFYING")
                try:
                    login_fn(
                        page,
                        username=username,
                        password=self.account["password"],
                        totp_secret=self.account.get("totp_secret"),
                    )
                    logger.info("[%s] Automated %s login succeeded", username, platform)
                    self._heartbeat("login_ok", status="ACTIVE")
                except CaptchaEncountered as exc:
                    logger.error("[%s] CAPTCHA during login: %s", username, exc)
                    self._take_failure_screenshot(page, "captcha")
                    self._heartbeat("login_captcha", status="NEEDS_REAUTH", error=str(exc))
                    raise
                except LoginFailed as exc:
                    logger.error("[%s] Login failed: %s", username, exc)
                    self._take_failure_screenshot(page, "login_failed")
                    self._heartbeat("login_failed", status="FAILED", error=str(exc))
                    raise
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass

    def process_one(self) -> bool:
        """Claim and post one job for this account.

        Returns True if a job was processed (successfully or not), False when
        the queue was empty.
        """
        if self._context is None:
            logger.warning(
                "[%s] process_one called before bootstrap — skipping",
                self.account["username"],
            )
            return False

        account_id = self.account["id"]
        username = self.account["username"]

        try:
            job = self._client.claim_next(
                stale_after_seconds=self._config.claim_stale_after_seconds,
                account_id=account_id,
            )
        except BackendError as exc:
            logger.error("[%s] Failed to claim next job: %s", username, exc)
            return False

        if not job:
            return False

        reply_id = job["reply_id"]
        self._heartbeat(f"claim_{reply_id}")
        logger.info(
            "[%s] Claimed reply_id=%s target_type=%s target_url=%s",
            username,
            reply_id,
            job.get("target_type"),
            job.get("target_url"),
        )

        platform = (self.account.get("platform") or "reddit").lower()
        job_platform = (job.get("platform") or platform).lower()

        try:
            if job_platform == "glp":
                result = glp_post_reply(
                    self._context,
                    job,
                    screenshot_dir=self._config.screenshot_dir,
                )
            elif job_platform == "chan":
                result = self._chan_post_with_pass_retry(job, reply_id, username)
            else:
                result = post_reply(
                    self._context,
                    job,
                    use_old_reddit=self._config.use_old_reddit,
                    screenshot_dir=self._config.screenshot_dir,
                )
        except ChanBanned as exc:
            logger.error("[%s] 4chan banned on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"banned_{reply_id}", status="BANNED", error=str(exc))
            self._safe_mark_failed(reply_id, f"banned: {exc}", requeue=False)
            return True
        except ChanFloodControl as exc:
            logger.warning("[%s] 4chan flood control on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"flood_{reply_id}")
            cooldown = exc.retry_after_seconds or 300
            try:
                self._client.bump_cooldown(self.account["id"], cooldown)
            except BackendError:
                logger.exception("[%s] Failed to bump cooldown after flood", username)
            self._safe_mark_failed(reply_id, f"flood: {exc}", requeue=True)
            return True
        except ChanThreadDead as exc:
            logger.info("[%s] 4chan thread dead on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"dead_{reply_id}")
            self._safe_mark_failed(reply_id, f"thread_dead: {exc}", requeue=False)
            return True
        except GlpBanned as exc:
            logger.error("[%s] GLP banned on reply_id=%s: %s", username, reply_id, exc)
            # status=BANNED flips is_enabled=False server-side, which removes
            # this account from the claim loop until an operator re-enables it.
            self._heartbeat(f"banned_{reply_id}", status="BANNED", error=str(exc))
            self._safe_mark_failed(reply_id, f"banned: {exc}", requeue=False)
            return True
        except GlpFloodControl as exc:
            logger.warning("[%s] GLP flood control on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"flood_{reply_id}")
            # If the rejection told us a precise retry-after, honor it; else
            # default to a 10-min penalty box for this account.
            cooldown = exc.retry_after_seconds or 600
            try:
                self._client.bump_cooldown(self.account["id"], cooldown)
            except BackendError:
                logger.exception("[%s] Failed to bump cooldown after flood", username)
            self._safe_mark_failed(reply_id, f"flood: {exc}", requeue=True)
            return True
        except PostCaptcha as exc:
            logger.warning("[%s] CAPTCHA on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"captcha_{reply_id}")
            self._safe_mark_failed(reply_id, str(exc), requeue=True)
            return True
        except PostingError as exc:
            logger.error("[%s] Posting error on reply_id=%s: %s", username, reply_id, exc)
            self._heartbeat(f"failed_{reply_id}")
            self._safe_mark_failed(reply_id, str(exc), requeue=True)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Unexpected error on reply_id=%s", username, reply_id)
            self._heartbeat(f"failed_{reply_id}")
            self._safe_mark_failed(reply_id, f"Unexpected: {exc}", requeue=True)
            return True

        self._heartbeat(f"post_{reply_id}")
        try:
            self._client.mark_posted(
                reply_id,
                posted_reddit_comment_id=result.get("posted_reddit_comment_id"),
                posted_platform_comment_id=result.get("posted_platform_comment_id"),
                posted_url=result.get("posted_url"),
            )
            logger.info("[%s] Marked reply_id=%s POSTED", username, reply_id)
            self._heartbeat(f"posted_{reply_id}")
        except BackendError:
            logger.exception("[%s] Failed to mark reply %s posted", username, reply_id)
        return True

    def shutdown(self) -> None:
        """Close the browser context cleanly."""
        if self._context is not None:
            try:
                self._context.close()
                logger.info("[%s] Context closed", self.account["username"])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[%s] Error closing context", self.account["username"]
                )
            finally:
                self._context = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _heartbeat(
        self,
        action: str,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        """Send a heartbeat to the backend. Swallows all errors so the main
        loop is never interrupted by a transient heartbeat failure."""
        try:
            self._client.heartbeat(
                account_id=self.account["id"],
                last_action=action,
                status=status,
                last_error=error,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[%s] Heartbeat failed (action=%r): %s",
                self.account["username"],
                action,
                exc,
            )

    def _take_failure_screenshot(self, page, label: str) -> None:
        """Capture a screenshot to screenshot_dir on failure paths."""
        try:
            os.makedirs(self._config.screenshot_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            account_id = self.account["id"]
            username = self.account["username"]
            filename = f"login_{account_id}_{username}_{label}_{ts}.png"
            path = os.path.join(self._config.screenshot_dir, filename)
            page.screenshot(path=path, full_page=True)
            logger.info("[%s] Screenshot saved: %s", username, path)
        except Exception:  # noqa: BLE001
            logger.exception("[%s] Failed to take failure screenshot", self.account["username"])

    def _safe_mark_failed(
        self, reply_id: int, error: str, requeue: bool = True
    ) -> None:
        try:
            self._client.mark_failed(reply_id, error, requeue=requeue)
        except BackendError:
            logger.exception(
                "[%s] Failed to mark reply %s failed", self.account["username"], reply_id
            )
