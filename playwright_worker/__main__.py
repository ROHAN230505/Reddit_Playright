"""CLI entrypoint:  python -m playwright_worker <command>

Commands:
    login       — open a browser so you can log into Reddit once. The
                  session is persisted in USER_DATA_DIR for later runs.
    run --once  — claim and process a single job, then exit.
    run         — continuous polling loop (Ctrl-C to stop).
"""

from __future__ import annotations

import argparse
import logging
import sys

from .browser import run_login_helper
from .config import WorkerConfig
from .runner import run_loop, run_once


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    config = WorkerConfig.from_env()

    parser = argparse.ArgumentParser(prog="playwright_worker")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Open a browser to manually sign in to Reddit.")

    run_p = sub.add_parser("run", help="Run the posting worker.")
    run_p.add_argument("--once", action="store_true", help="Process one job then exit.")

    args = parser.parse_args(argv)

    if args.command == "login":
        run_login_helper(config.user_data_dir, config.browser_channel)
        return 0

    if args.command == "run":
        if args.once:
            did_work = run_once(config)
            return 0 if did_work else 0  # success either way; absence of work isn't an error
        run_loop(config)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
