"""Seed 4chan posting "accounts".

4chan posting is anonymous — there is no username/password login. A 4chan
"account" here is just a posting *slot* the worker uses to claim and post
chan-platform replies: it owns a browser-fingerprint profile, a user-data-dir,
and per-account flood-control rate limits. The only real credential is the
shared 4chan Pass, which is configured worker-side via the CHAN_PASS_TOKEN /
CHAN_PASS_PIN env vars (not per-account), so the worker authenticates the Pass
through the slot's (proxied) browser context at bootstrap.

Because there's no login, these slots are created status=ACTIVE and are
immediately claimable by the worker (claim eligibility only checks is_enabled +
platform + rate limits, not status). The username/password columns are
non-nullable in the schema, so we store a synthetic username and a placeholder
encrypted password that is never used to log in anywhere.

assigned_sections is set to the configured boards (settings.chan_boards, env
CHAN_BOARDS — default "g,biz") so each slot only works those boards. The chan
scraper tags every Reply with its board in platform_section, so this filter
matches what the claim path compares against.

Run from the backend/ directory:
    python -m scripts.seed_chan_accounts
Idempotent: existing usernames are skipped. Pass a count to create more slots:
    python -m scripts.seed_chan_accounts 3
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import settings
from app.db.models import RedditAccount
from app.db.session import SessionLocal
from app.routes.accounts import _profile_dir
from app.services import crypto
from app.services.profile_pool import pick_next_profile_index

# 4chan per-platform conservative defaults — mirrors create_account() for the
# "chan" branch in app/routes/accounts.py. 4chan flood control is ~60s between
# posts per board; we stay well clear so the cadence reads as human.
CHAN_DEFAULTS = {
    "posts_per_hour_limit": 3,
    "posts_per_day_limit": 20,
    "min_seconds_between_posts": 300,   # 5 min
    "max_seconds_between_posts": 900,   # 15 min
}

# Synthetic slot names. 4chan posting is anonymous so these never appear on the
# site; they only key the DB record and the per-slot browser profile dir.
SLOT_PREFIX = "chan_slot_"

# Placeholder password — never used for any login (chan is anonymous). Stored
# encrypted only because the column is non-nullable.
PLACEHOLDER_PASSWORD = "ANONYMOUS_NO_LOGIN"


def main() -> None:
    count = 1
    if len(sys.argv) > 1:
        try:
            count = max(1, int(sys.argv[1]))
        except ValueError:
            print(f"Ignoring non-integer count {sys.argv[1]!r}; defaulting to 1.")

    assigned_sections = ",".join(settings.chan_boards) or None

    db = SessionLocal()
    created: list[str] = []
    skipped: list[str] = []
    try:
        used = [
            row[0]
            for row in db.execute(
                select(RedditAccount.profile_index).where(
                    RedditAccount.is_enabled == True  # noqa: E712
                )
            ).all()
            if row[0] is not None
        ]

        # Pick the next free slot numbers (skip any that already exist).
        existing_names = {
            row[0]
            for row in db.execute(select(RedditAccount.username)).all()
        }
        made = 0
        n = 1
        while made < count:
            username = f"{SLOT_PREFIX}{n}"
            n += 1
            if username in existing_names:
                skipped.append(username)
                continue

            profile_index = pick_next_profile_index(used)
            used.append(profile_index)

            account = RedditAccount(
                username=username,
                password_enc=crypto.encrypt(PLACEHOLDER_PASSWORD),
                totp_secret_enc=None,
                proxy_id=None,
                # No login step for chan — the slot is usable immediately.
                status="ACTIVE",
                is_enabled=True,
                user_data_dir=_profile_dir(username),
                profile_index=profile_index,
                platform="chan",
                assigned_sections=assigned_sections,
                **CHAN_DEFAULTS,
            )
            db.add(account)
            db.flush()
            created.append(
                f"{username} (id={account.id}, profile_index={profile_index}, "
                f"boards={assigned_sections})"
            )
            made += 1

        db.commit()
    finally:
        db.close()

    print(f"4chan slot seed complete: {len(created)} created, {len(skipped)} skipped.")
    for line in created:
        print(f"  + created  {line}")
    for line in skipped:
        print(f"  = skipped  {line} (already exists)")
    if created:
        print(
            "\nThe 4chan Pass is shared and configured worker-side via "
            "CHAN_PASS_TOKEN / CHAN_PASS_PIN — no per-slot credential needed. "
            "Assign a proxy to each slot via the dashboard if you want posts to "
            "egress from a specific IP (the Pass binds to that IP)."
        )


if __name__ == "__main__":
    main()
