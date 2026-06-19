"""CLI entrypoint:  python -m playwright_worker <command>

Commands:
    login                 — open a browser so you can log into Reddit once.
    glp-login             — open a browser so you can log into GLP once and
                            save storage_state for the scraper.
    run [--once]          — claim and process job(s). Dispatches to the right
                            poster based on each job's `platform` field.
    run --platform=glp    — informational; the runner already dispatches per-job,
                            but this lets ops scope a worker to one platform.
    account-run           — run the multi-account runtime for one account id.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .browser import run_login_helper
from .account_runtime import AccountRuntime
from .client import BackendClient
from .config import WorkerConfig
from .runner import run_loop, run_once


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def _run_glp_login_helper(user_data_dir: str, channel: str | None) -> None:
    """Open a non-headless GLP login page so the operator can sign in once.
    The persistent context preserves cookies for subsequent scraper/poster runs."""
    import os
    from patchright.sync_api import sync_playwright

    os.makedirs(user_data_dir, exist_ok=True)
    with sync_playwright() as p:
        launch_kwargs: dict = {
            "user_data_dir": user_data_dir,
            "headless": False,
            "args": ["--no-default-browser-check", "--no-first-run"],
        }
        if channel:
            launch_kwargs["channel"] = channel
        ctx = p.chromium.launch_persistent_context(**launch_kwargs)
        page = ctx.new_page()
        page.goto("https://www.godlikeproductions.com/login.php")
        print(
            "Browser is open. Sign in to GLP, then close the window when done. "
            "Cookies will persist in the profile dir for the worker to reuse."
        )
        # Block until the operator closes the last page.
        try:
            while ctx.pages:
                page.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001
            pass
        ctx.close()


def _load_account(config: WorkerConfig, account_id: int) -> dict:
    client = BackendClient(
        base_url=config.backend_base_url,
        worker_name=config.worker_name,
        timeout=config.request_timeout_seconds,
    )
    for account in client.list_active_accounts(platform="reddit"):
        if int(account.get("id")) == account_id:
            return account
    raise RuntimeError(f"Reddit account id={account_id} is not active or enabled")


def _run_account_runtime(config: WorkerConfig, account_id: int, once: bool) -> int:
    from patchright.sync_api import sync_playwright

    logger = logging.getLogger(__name__)
    account = _load_account(config, account_id)
    logger.info(
        "Starting account-scoped Reddit worker account_id=%s username=%s once=%s",
        account.get("id"),
        account.get("username"),
        once,
    )

    with sync_playwright() as playwright:
        runtime = AccountRuntime(
            playwright,
            account,
            config,
            lambda: BackendClient(
                base_url=config.backend_base_url,
                worker_name=config.worker_name,
                timeout=config.request_timeout_seconds,
            ),
        )
        try:
            runtime.bootstrap()
            while True:
                did_work = runtime.process_one()
                if once:
                    return 0
                if not did_work:
                    time.sleep(config.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Account worker interrupted, shutting down.")
            return 0
        finally:
            runtime.shutdown()


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    config = WorkerConfig.from_env()

    parser = argparse.ArgumentParser(prog="playwright_worker")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Open a browser to manually sign in to Reddit.")
    sub.add_parser("glp-login", help="Open a browser to manually sign in to GLP.")

    run_p = sub.add_parser("run", help="Run the posting worker.")
    run_p.add_argument("--once", action="store_true", help="Process one job then exit.")
    run_p.add_argument(
        "--platform",
        choices=("reddit", "glp", "chan"),
        default=None,
        help=(
            "Scope this worker to one platform. When set, the backend only hands "
            "out jobs for that platform — e.g. --platform=chan posts only 4chan "
            "replies and never touches Reddit/GLP. Defaults to env WORKER_PLATFORM."
        ),
    )

    account_p = sub.add_parser(
        "account-run",
        help="Run the account-scoped Reddit worker for one account id.",
    )
    account_p.add_argument("--account-id", type=int, required=True)
    account_p.add_argument("--once", action="store_true", help="Process one job then exit.")

    args = parser.parse_args(argv)

    if args.command == "login":
        run_login_helper(config.user_data_dir, config.browser_channel)
        return 0

    if args.command == "glp-login":
        _run_glp_login_helper(config.user_data_dir, config.browser_channel)
        return 0

    if args.command == "run":
        import os
        platform = args.platform or (os.getenv("WORKER_PLATFORM") or "").strip().lower() or None
        if platform:
            logging.getLogger(__name__).info("Worker scoped to platform=%s", platform)
        if args.once:
            did_work = run_once(config, platform=platform)
            return 0 if did_work else 0  # success either way; absence of work isn't an error
        run_loop(config, platform=platform)
        return 0

    if args.command == "account-run":
        return _run_account_runtime(config, account_id=args.account_id, once=args.once)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
