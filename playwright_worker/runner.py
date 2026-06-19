"""Worker orchestration: claim → post → report."""

from __future__ import annotations

import logging
import time

from .browser import persistent_context
from .client import BackendClient, BackendError
from .config import WorkerConfig
from .chan_poster import ChanBanned, ChanFloodControl, ChanThreadDead
from .chan_poster import post_reply as chan_post_reply
from .glp_poster import GlpBanned, GlpFloodControl
from .glp_poster import post_reply as glp_post_reply
from .poster import CaptchaEncountered, PostingError, RedditWarmupConfig, post_reply

logger = logging.getLogger(__name__)


def _process_one(
    config: WorkerConfig,
    client: BackendClient,
    context,
    platform: str | None = None,
    account_id: int | None = None,
) -> bool:
    """Claim and process a single job. Returns True if work was done,
    False if the queue was empty. `platform` scopes claims to one platform
    (e.g. 'chan') so this worker never touches other platforms' replies.
    `account_id` identifies the slot so the backend enforces its rate limits
    and cooldown (without it, posting is unthrottled)."""
    try:
        job = client.claim_next(
            stale_after_seconds=config.claim_stale_after_seconds,
            platform=platform,
            account_id=account_id,
        )
    except BackendError as exc:
        logger.error("Failed to claim next job: %s", exc)
        return False

    if not job:
        return False

    reply_id = job["reply_id"]
    logger.info(
        "Claimed reply_id=%s target_type=%s target_url=%s",
        reply_id,
        job.get("target_type"),
        job.get("target_url"),
    )

    job_platform = (job.get("platform") or "reddit").lower()

    try:
        if job_platform == "glp":
            result = glp_post_reply(
                context,
                job,
                screenshot_dir=config.screenshot_dir,
            )
        elif job_platform == "chan":
            try:
                result = chan_post_reply(
                    context, job, screenshot_dir=config.screenshot_dir
                )
            except CaptchaEncountered:
                # Stale Pass cookie / rotated IP — re-auth once and retry.
                if config.chan_pass_token and config.chan_pass_pin:
                    from .chan_auth import ChanPassError, ensure_authenticated
                    logger.warning("4chan captcha on reply_id=%s — re-authing Pass", reply_id)
                    try:
                        ensure_authenticated(
                            context, config.chan_pass_token, config.chan_pass_pin, force=True
                        )
                    except ChanPassError as exc:
                        logger.error("Pass re-auth failed: %s", exc)
                        raise CaptchaEncountered(str(exc)) from exc
                    result = chan_post_reply(
                        context, job, screenshot_dir=config.screenshot_dir
                    )
                else:
                    raise
        else:
            result = post_reply(
                context,
                job,
                use_old_reddit=config.use_old_reddit,
                screenshot_dir=config.screenshot_dir,
                warmup_config=RedditWarmupConfig(
                    enabled=config.reddit_warmup_enabled,
                    pre_reply_delay_min_seconds=config.reddit_pre_reply_delay_min_seconds,
                    pre_reply_delay_max_seconds=config.reddit_pre_reply_delay_max_seconds,
                    read_delay_min_seconds=config.reddit_read_delay_min_seconds,
                    read_delay_max_seconds=config.reddit_read_delay_max_seconds,
                    scroll_steps_min=config.reddit_scroll_steps_min,
                    scroll_steps_max=config.reddit_scroll_steps_max,
                ),
            )
    except ChanBanned as exc:
        logger.error("4chan banned on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, f"banned: {exc}", requeue=False)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except ChanFloodControl as exc:
        logger.warning("4chan flood on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, f"flood: {exc}", requeue=True)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except ChanThreadDead as exc:
        logger.info("4chan thread dead on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, f"thread_dead: {exc}", requeue=False)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except GlpBanned as exc:
        logger.error("GLP banned on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, f"banned: {exc}", requeue=False)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except GlpFloodControl as exc:
        logger.warning("GLP flood control on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, f"flood: {exc}", requeue=True)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except CaptchaEncountered as exc:
        logger.warning("CAPTCHA on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, str(exc), requeue=True)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except PostingError as exc:
        logger.error("Posting error on reply_id=%s: %s", reply_id, exc)
        try:
            client.mark_failed(reply_id, str(exc), requeue=True)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error on reply_id=%s", reply_id)
        try:
            client.mark_failed(reply_id, f"Unexpected: {exc}", requeue=True)
        except BackendError:
            logger.exception("Failed to mark reply %s failed", reply_id)
        return True

    try:
        client.mark_posted(
            reply_id,
            posted_reddit_comment_id=result.get("posted_reddit_comment_id"),
            posted_platform_comment_id=result.get("posted_platform_comment_id"),
            posted_url=result.get("posted_url"),
        )
        logger.info("Marked reply_id=%s POSTED", reply_id)
    except BackendError:
        logger.exception("Failed to mark reply %s posted", reply_id)
    return True


def _auth_chan_pass(config: WorkerConfig, context) -> None:
    """Authenticate the 4chan Pass on a fresh context, if configured. Best-effort:
    a bad Pass logs an error but doesn't stop the worker — posts then hit the
    captcha and surface CaptchaEncountered as before."""
    if not (config.chan_pass_token and config.chan_pass_pin):
        return
    from .chan_auth import ChanPassError, ensure_authenticated
    try:
        ensure_authenticated(context, config.chan_pass_token, config.chan_pass_pin)
        logger.info("4chan Pass authenticated for worker context")
    except ChanPassError as exc:
        logger.error("4chan Pass auth failed: %s", exc)


def _resolve_slot_account_id(client: BackendClient, platform: str | None) -> int | None:
    """For a platform-scoped worker, find the slot whose rate limits the backend
    should enforce. Returns the first enabled account on that platform, or None
    (None = unthrottled — only happens if no slot is seeded). Best-effort: a
    backend error logs and returns None rather than blocking startup."""
    if not platform:
        return None
    try:
        accounts = client.list_active_accounts(platform=platform)
    except BackendError as exc:
        logger.warning("Could not resolve %s slot account_id: %s", platform, exc)
        return None
    if not accounts:
        logger.warning(
            "No enabled %s account/slot found — posting will be UNTHROTTLED. "
            "Seed one (e.g. scripts.seed_chan_accounts) to enforce rate limits.",
            platform,
        )
        return None
    acct = accounts[0]
    logger.info("%s worker bound to slot id=%s (%s) for rate limiting",
                platform, acct.get("id"), acct.get("username"))
    return acct.get("id")


def run_once(config: WorkerConfig, platform: str | None = None) -> bool:
    """Process a single job (or return False if none). Useful for tests
    and for `python -m playwright_worker run --once`. `platform` scopes claims."""
    client = BackendClient(
        base_url=config.backend_base_url,
        worker_name=config.worker_name,
        timeout=config.request_timeout_seconds,
    )
    account_id = _resolve_slot_account_id(client, platform)
    with persistent_context(
        config.user_data_dir,
        headless=config.headless,
        channel=config.browser_channel,
    ) as context:
        _auth_chan_pass(config, context)
        return _process_one(config, client, context, platform=platform, account_id=account_id)


def run_loop(config: WorkerConfig, platform: str | None = None) -> None:
    """Continuous polling loop. Exits cleanly on KeyboardInterrupt. `platform`
    scopes every claim so this worker only ever posts to that platform."""
    client = BackendClient(
        base_url=config.backend_base_url,
        worker_name=config.worker_name,
        timeout=config.request_timeout_seconds,
    )
    account_id = _resolve_slot_account_id(client, platform)
    logger.info(
        "Starting Playwright worker name=%s backend=%s poll=%ss platform=%s account_id=%s",
        config.worker_name,
        config.backend_base_url,
        config.poll_interval_seconds,
        platform,
        account_id,
    )
    with persistent_context(
        config.user_data_dir,
        headless=config.headless,
        channel=config.browser_channel,
    ) as context:
        _auth_chan_pass(config, context)
        while True:
            try:
                did_work = _process_one(
                    config, client, context, platform=platform, account_id=account_id
                )
            except KeyboardInterrupt:
                logger.info("Worker interrupted, shutting down.")
                return
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected error in worker loop, sleeping then continuing.")
                did_work = False

            if not did_work:
                try:
                    time.sleep(config.poll_interval_seconds)
                except KeyboardInterrupt:
                    logger.info("Worker interrupted, shutting down.")
                    return
