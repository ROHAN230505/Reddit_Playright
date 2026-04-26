"""Worker orchestration: claim → post → report."""

from __future__ import annotations

import logging
import time

from .browser import persistent_context
from .client import BackendClient, BackendError
from .config import WorkerConfig
from .poster import CaptchaEncountered, PostingError, post_reply

logger = logging.getLogger(__name__)


def _process_one(
    config: WorkerConfig,
    client: BackendClient,
    context,
) -> bool:
    """Claim and process a single job. Returns True if work was done,
    False if the queue was empty."""
    try:
        job = client.claim_next(stale_after_seconds=config.claim_stale_after_seconds)
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

    try:
        result = post_reply(
            context,
            job,
            use_old_reddit=config.use_old_reddit,
            screenshot_dir=config.screenshot_dir,
        )
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
        client.mark_posted(reply_id, result.get("posted_reddit_comment_id"))
        logger.info("Marked reply_id=%s POSTED", reply_id)
    except BackendError:
        logger.exception("Failed to mark reply %s posted", reply_id)
    return True


def run_once(config: WorkerConfig) -> bool:
    """Process a single job (or return False if none). Useful for tests
    and for `python -m playwright_worker run --once`."""
    client = BackendClient(
        base_url=config.backend_base_url,
        worker_name=config.worker_name,
        timeout=config.request_timeout_seconds,
    )
    with persistent_context(
        config.user_data_dir,
        headless=config.headless,
        channel=config.browser_channel,
    ) as context:
        return _process_one(config, client, context)


def run_loop(config: WorkerConfig) -> None:
    """Continuous polling loop. Exits cleanly on KeyboardInterrupt."""
    client = BackendClient(
        base_url=config.backend_base_url,
        worker_name=config.worker_name,
        timeout=config.request_timeout_seconds,
    )
    logger.info(
        "Starting Playwright worker name=%s backend=%s poll=%ss",
        config.worker_name,
        config.backend_base_url,
        config.poll_interval_seconds,
    )
    with persistent_context(
        config.user_data_dir,
        headless=config.headless,
        channel=config.browser_channel,
    ) as context:
        while True:
            try:
                did_work = _process_one(config, client, context)
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
