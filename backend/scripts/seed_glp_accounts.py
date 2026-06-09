"""Seed the six GodlikeProductions (GLP) accounts.

These are existing, high-reputation ("godlike") GLP forum accounts that we want
to continue working with. This script registers them in the system the same way
POST /accounts would, so the worker/processor can hand them GLP replies.

Mapping (GLP username -> Dolphin Anty profile, for operator reference only):
    veltrix92      -> godlike_veltrix
    orionvale66    -> godlike_orion
    nordbyte84     -> godlike_lucas
    HudsonPixelX   -> godlike_hudson
    azuron71       -> godlike_Moreau
    maplegrid88    -> godlike_liam

We do NOT log into these accounts here — this only creates the DB records. The
Dolphin Anty profile name has no column in the schema, so it lives in this
mapping for reference; accounts are keyed by their GLP username.

Notes:
- platform="glp" so the worker only ever hands them GLP replies, and they get
  GLP's conservative rate-limit defaults (2/hour, 12/day, 600-1800s cadence).
- assigned_sections is set to the tech topic ("Science/Technology") so these
  accounts only ever work tech/AI threads. The GLP scraper now pulls from the
  configured tech topic page(s) (settings.glp_topics) and tags each thread with
  that slug, so this filter actually matches. GLP has no dedicated AI forum;
  AI discussion lives inside Science/Technology and general threads, so the
  Technology topic is the on-target section.
- profile_index is round-robin assigned against currently enabled accounts,
  matching the POST /accounts behaviour.
- Passwords are unknown here, so a placeholder is stored encrypted. Update each
  account's real password later via PATCH /accounts/{id} (or the dashboard);
  status stays NEW until then. We never attempt a login.

Run from the backend/ directory:
    python -m scripts.seed_glp_accounts
Idempotent: existing usernames are skipped.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import RedditAccount
from app.db.session import SessionLocal
from app.routes.accounts import _profile_dir
from app.services import crypto
from app.services.profile_pool import pick_next_profile_index

# GLP per-platform conservative defaults — mirrors create_account() in
# app/routes/accounts.py. GLP moderation is more aggressive than Reddit's.
GLP_DEFAULTS = {
    "posts_per_hour_limit": 2,
    "posts_per_day_limit": 12,
    "min_seconds_between_posts": 600,   # 10 min
    "max_seconds_between_posts": 1800,  # 30 min
}

# (glp_username, dolphin_anty_profile_for_reference)
GLP_ACCOUNTS = [
    ("veltrix92", "godlike_veltrix"),
    ("orionvale66", "godlike_orion"),
    ("nordbyte84", "godlike_lucas"),
    ("HudsonPixelX", "godlike_hudson"),
    ("azuron71", "godlike_Moreau"),
    ("maplegrid88", "godlike_liam"),
]

# Placeholder password stored (encrypted) until the real one is set. Cannot be a
# real login — accounts stay NEW until an operator updates the password.
PLACEHOLDER_PASSWORD = "CHANGE_ME"

# Tech/AI only: restrict these accounts to GLP's tech topic. The scraper
# (process_glp) pulls from /topics/Science/Technology and tags every thread with
# this slug, so the value matches what lands in Reply.platform_section. Keep in
# sync with settings.glp_topics (env GLP_TOPICS).
ASSIGNED_SECTIONS = "Science/Technology"


def main() -> None:
    db = SessionLocal()
    created: list[str] = []
    skipped: list[str] = []
    try:
        # Seed the round-robin pool from currently enabled accounts, same as the
        # API endpoint does.
        used = [
            row[0]
            for row in db.execute(
                select(RedditAccount.profile_index).where(
                    RedditAccount.is_enabled == True  # noqa: E712
                )
            ).all()
            if row[0] is not None
        ]

        for username, anty_profile in GLP_ACCOUNTS:
            existing = db.scalar(
                select(RedditAccount).where(RedditAccount.username == username)
            )
            if existing:
                skipped.append(f"{username} (id={existing.id})")
                continue

            profile_index = pick_next_profile_index(used)
            used.append(profile_index)

            account = RedditAccount(
                username=username,
                password_enc=crypto.encrypt(PLACEHOLDER_PASSWORD),
                totp_secret_enc=None,
                proxy_id=None,
                status="NEW",
                is_enabled=True,
                user_data_dir=_profile_dir(username),
                profile_index=profile_index,
                platform="glp",
                assigned_sections=ASSIGNED_SECTIONS,  # tech/AI only
                **GLP_DEFAULTS,
            )
            db.add(account)
            db.flush()  # populate id for the report
            created.append(
                f"{username} (id={account.id}, profile_index={profile_index}, "
                f"anty={anty_profile})"
            )

        db.commit()
    finally:
        db.close()

    print(f"GLP account seed complete: {len(created)} created, {len(skipped)} skipped.")
    for line in created:
        print(f"  + created  {line}")
    for line in skipped:
        print(f"  = skipped  {line} (already exists)")
    if created:
        print(
            "\nNext: set each account's real password via PATCH /accounts/{id} "
            "or the dashboard. They stay status=NEW until then. No login is "
            "attempted by this script."
        )


if __name__ == "__main__":
    main()
