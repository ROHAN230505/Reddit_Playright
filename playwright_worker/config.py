"""Environment-driven configuration for the Playwright worker."""

import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on", "y")


@dataclass(frozen=True)
class WorkerConfig:
    backend_base_url: str
    worker_name: str
    poll_interval_seconds: int
    claim_stale_after_seconds: int
    user_data_dir: str
    browser_channel: str | None
    headless: bool
    screenshot_dir: str
    request_timeout_seconds: int
    use_old_reddit: bool
    submit_post_url_fallback_to_new: bool
    reddit_warmup_enabled: bool
    reddit_pre_reply_delay_min_seconds: float
    reddit_pre_reply_delay_max_seconds: float
    reddit_read_delay_min_seconds: float
    reddit_read_delay_max_seconds: float
    reddit_scroll_steps_min: int
    reddit_scroll_steps_max: int
    # 4chan Pass — authenticates the browser context so posts skip the per-post
    # reCAPTCHA. A Pass is bound to ONE IP at a time, so the worker re-auths
    # (via the same proxied context) at bootstrap and again if a captcha appears.
    chan_pass_token: str | None
    chan_pass_pin: str | None

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            backend_base_url=os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/"),
            worker_name=os.getenv("PLAYWRIGHT_WORKER_NAME", "playwright-local"),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "20")),
            claim_stale_after_seconds=int(os.getenv("CLAIM_STALE_AFTER_SECONDS", "600")),
            user_data_dir=os.getenv("USER_DATA_DIR", os.path.expanduser("~/.reddit-worker-profile")),
            browser_channel=os.getenv("BROWSER_CHANNEL", "chrome") or None,
            headless=_bool(os.getenv("HEADLESS"), default=False),
            screenshot_dir=os.getenv("SCREENSHOT_DIR", os.path.abspath("./worker-screenshots")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
            use_old_reddit=_bool(os.getenv("USE_OLD_REDDIT"), default=True),
            submit_post_url_fallback_to_new=_bool(
                os.getenv("FALLBACK_TO_NEW_REDDIT"), default=False
            ),
            reddit_warmup_enabled=_bool(os.getenv("REDDIT_WARMUP_ENABLED"), default=True),
            reddit_pre_reply_delay_min_seconds=float(
                os.getenv("REDDIT_PRE_REPLY_DELAY_MIN_SECONDS", "3")
            ),
            reddit_pre_reply_delay_max_seconds=float(
                os.getenv("REDDIT_PRE_REPLY_DELAY_MAX_SECONDS", "9")
            ),
            reddit_read_delay_min_seconds=float(
                os.getenv("REDDIT_READ_DELAY_MIN_SECONDS", "4")
            ),
            reddit_read_delay_max_seconds=float(
                os.getenv("REDDIT_READ_DELAY_MAX_SECONDS", "12")
            ),
            reddit_scroll_steps_min=int(os.getenv("REDDIT_SCROLL_STEPS_MIN", "2")),
            reddit_scroll_steps_max=int(os.getenv("REDDIT_SCROLL_STEPS_MAX", "5")),
            chan_pass_token=(os.getenv("CHAN_PASS_TOKEN") or "").strip() or None,
            chan_pass_pin=(os.getenv("CHAN_PASS_PIN") or "").strip() or None,
        )
