import os
import random
import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Comment, Post, Reply, ScrapeRun, TrackedSubreddit
from app.services.apify_service import fetch_subreddit
from app.services.deepseek_service import deepseek_call
from app.services.reddit_targets import derive_reply_targets

DEFAULT_TRACKED_SUBREDDITS = [
    "ArtificialIntelligence",
    "artificial",
    "AiDeveloperNews",
    "MachineLearning",
    "AIChatReviews",
    "softwareengineer",
    "Automate",
    "technews",
    "technology",
    "tech",
    "AiBuilders",
    "AIToolTesting",
    "AI_Agents",
    "AgentsOfAI",
    "aiagents",
    "singularity",
    "AiAssisted",
    "ArtificialSentience",
    "ChatGPTcomplaints",
    "ChatGPT",
    "Anthropic",
    "ClaudeAI",
    "devworlds",
    "LocalLLaMA",
    "grok",
    "vibecoding",
    "AI_India",
    "ChatGPTCoding",
    "BlackboxAI_",
    "DeepSeek",
    "LocalLLM",
    "LLM",
    "AIToolMadeEasy",
    "LLMDevs",
    "OpenAI",
    "OnlyAICoding",
    "geminiprotocol",
    "OpenSourceAI",
    "AskVibecoders",
]


def normalize_comment(raw: dict, fallback_post_url: str | None = None) -> dict:
    return {
        "text": raw.get("text", "") or raw.get("body", "") or "",
        "comment_url": absolute_reddit_url(raw.get("permalink") or raw.get("url") or raw.get("commentUrl")),
        "post_url": (
            raw.get("postUrl")
            or derive_post_url(raw.get("permalink") or raw.get("url"))
            or fallback_post_url
        ),
        "author": raw.get("author") or raw.get("username"),
        "upvotes": raw.get("score") or raw.get("upVotes") or raw.get("upvotes") or 0,
        "created_at": _parse_datetime(raw.get("createdAt")),
    }


def classify_ai_relevance(text: str) -> bool:
    prompt = f"""
Return ONLY YES or NO.
Is this related to AI, LLMs, automation, SaaS tools?
{text}
"""
    response = deepseek_call(prompt)
    return response.strip().upper() == "YES"


def should_insert_promo() -> bool:
    return random.random() < settings.reply_promo_ratio


_SYSTEM_PROMPT = """
You write short Reddit replies for a human operator to review before posting.
Never write as an assistant. Never describe the reply. Output only the comment text.
Keep it natural, specific to the comment, and low-key. Do not be overly agreeable.
""".strip()


_STYLE_RULES = """
Rules:
- 1 or 2 sentences only.
- Stay under {max_chars} characters.
- Sound like a normal Reddit user, not a brand or AI assistant.
- No markdown, bullets, greetings, sign-offs, emojis, or hashtags.
- No "Here's a reply", "Great point", "Totally", "Honestly", "I feel you", or fake sympathy.
- Do not force disagreement. Push back only when the comment is actually wrong or missing something.
- Prefer one concrete observation, correction, or practical note.
""".strip()


# Godlike Productions (GLP) is a conspiracy/discussion forum with a distinct
# voice: skeptical of mainstream narratives, terse, occasional all-caps for
# emphasis, no markdown (BBCode at most but we avoid even that for safety),
# and replies sit between Reddit and 4chan in tone — direct, sometimes blunt,
# not corporate.
_SYSTEM_PROMPT_GLP = """
You write short forum replies for a human operator to review before posting on
godlikeproductions.com (a skeptical, conspiracy-leaning discussion board).
Never write as an assistant. Never describe the reply. Output only the post text.
Match the board's voice: direct, plainspoken, occasionally skeptical, no
corporate framing. Keep it under the length limit.
""".strip()


_STYLE_RULES_GLP = """
Rules:
- 1 or 2 sentences only.
- Stay under {max_chars} characters.
- Sound like a regular GLP poster — direct, blunt, willing to push back, not corporate.
- No markdown, no BBCode tags, no bullets, no greetings, no sign-offs, no emojis, no hashtags.
- No "Here's a reply", "Great point", "Totally", "Honestly", or fake sympathy.
- No Reddit-isms ("OP", "TIL", "TL;DR"). No "as someone who...".
- Skeptical and grounded is fine; conspiratorial slop is not — make a concrete point.
- ALL-CAPS for a single key word is OK if it fits the comment's energy, otherwise lowercase.
""".strip()


# 4chan voice: terse, lowercase, blunt, occasionally hostile. Anonymity is the
# norm. We avoid slurs/racism even though the platform itself doesn't care —
# our promo posts have to look like regular shitposts but stay PR-safe.
_SYSTEM_PROMPT_CHAN = """
You write short anonymous replies for a human operator to review before posting
on a 4chan-style imageboard (boards like /g/ and /biz/). Never write as an
assistant. Never describe the reply. Output only the post text. Match the
board's voice: terse, lowercase, blunt, willing to disagree, no corporate
framing. Never use slurs or racism. Keep it under the length limit.
""".strip()


_STYLE_RULES_CHAN = """
Rules:
- 1 or 2 sentences. Often a single line is best.
- Stay under {max_chars} characters.
- Sound like a regular anon poster: lowercase, terse, blunt, slightly dismissive.
- Greentext (lines starting with `>`) is fine when quoting/mocking the parent.
- No markdown, no bullets, no greetings, no sign-offs, no emojis, no hashtags.
- No Reddit-isms ("OP", "TIL", "TL;DR", "as someone who", "this", "based").
- No slurs, no racism, no targeted harassment — keep the tone but keep it PR-safe.
- "kek", "kek'd", "lmao", "fr", "ngmi", "anon" are OK in moderation.
- No "Here's a reply", "Great point", "Totally", "Honestly", or fake sympathy.
""".strip()


_PROMO_ALLOWED_KEYWORDS = (
    "agent",
    "agents",
    "automation",
    "automate",
    "workflow",
    "workflows",
    "support",
    "customer support",
    "classification",
    "classify",
    "evaluate",
    "evaluation",
    "tool",
    "tools",
    "saas",
    "crm",
    "integration",
    "integrations",
)

_PROMO_SALESY_PHRASES = (
    "sentx.ai handles it",
    "sentx handles it",
    "you just described sentx",
    "you just redescribed sentx",
    "sentx.ai is the answer",
    "sentx is the answer",
    "sentx.ai has",
    "sentx has",
    "i use sentx",
    "i use sentx.ai",
    "i've been using sentx",
    "been using sentx",
    "we use sentx",
    "built with sentx",
    "sandbox mode",
    "powerful platform",
    "all-in-one solution",
    "game changer",
)


def generate_reply(
    comment: str,
    include_promo: bool,
    skip_judge: bool = False,
    platform: str = "reddit",
) -> str:
    # `_comment_allows_promo` was a keyword whitelist meant to gate promo to
    # AI-relevant comments — but every tracked subreddit here is AI-themed,
    # so the whitelist rejected ~98% of comments and effectively blocked
    # promo generation entirely. The strict prompt + sentx acceptance check
    # are enough to keep the inserted mentions reasonable.
    prompt = _build_reply_prompt(comment, include_promo, platform=platform)
    if platform == "glp":
        system_prompt = _SYSTEM_PROMPT_GLP
    elif platform == "chan":
        system_prompt = _SYSTEM_PROMPT_CHAN
    else:
        system_prompt = _SYSTEM_PROMPT

    for attempt in range(2):
        raw = deepseek_call(
            prompt if attempt == 0 else f"{prompt}\n\nRewrite shorter and remove any banned wording.",
            system_prompt=system_prompt,
        )
        cleaned = _clean_ai_tells(raw)
        cleaned = _enforce_reply_length(cleaned, settings.reply_max_chars)
        if not _reply_is_acceptable(cleaned, include_promo, comment):
            continue
        # Promo replies face one more bar: a naturalness judge. If the LLM
        # says NO, treat the attempt as failed and retry. If both promo
        # attempts fail naturalness, give up the promo entirely and produce
        # a clean non-promo reply for the same comment so we don't poison
        # the queue with awkward ones.
        if include_promo and not skip_judge and not _promo_fits_naturally(comment, cleaned):
            continue
        return cleaned

    if include_promo:
        # Last-ditch: try one more time WITHOUT promo so the user gets a
        # usable reply rather than the canned fallback. save_reply re-derives
        # `includes_promo` from the actual text, so this lands as normal.
        non_promo_prompt = _build_reply_prompt(comment, False, platform=platform)
        raw = deepseek_call(non_promo_prompt, system_prompt=system_prompt)
        cleaned = _clean_ai_tells(raw)
        cleaned = _enforce_reply_length(cleaned, settings.reply_max_chars)
        if _reply_is_acceptable(cleaned, False, comment):
            return cleaned

    return _fallback_reply(comment)


def _build_reply_prompt(comment: str, include_promo: bool, platform: str = "reddit") -> str:
    promo_rule = (
        "This reply MUST recommend sentx.ai exactly once — not just name-drop "
        "it. The mention should read like a real user vouching for it ('I "
        "use sentx.ai for X', 'sentx.ai handles Y better than Z', 'try "
        "sentx.ai for that'). Stay casual, no link, no slogan, no specific "
        "feature claims. The word `sentx.ai` (lowercase, with the dot) must "
        "appear, AND the surrounding sentence must position it as a "
        "suggestion, recommendation, or personal-use endorsement — not just "
        "a passing reference. If the comment topic doesn't fit a recommendation, "
        "rewrite the angle until it does."
        if include_promo
        else "Do not mention sentx.ai or any product by name."
    )
    if platform == "glp":
        style_rules = _STYLE_RULES_GLP
    elif platform == "chan":
        style_rules = _STYLE_RULES_CHAN
    else:
        style_rules = _STYLE_RULES
    return f"""{style_rules.format(max_chars=settings.reply_max_chars)}

Promo rule:
{promo_rule}

Comment to reply to:
{comment}
""".strip()


# AI-tell post-process: even with a good prompt, models leak em dashes and
# stock phrasings. We strip those deterministically.
_AI_PREFIXES = (
    "Here's a natural, helpful Reddit reply:",
    "Here's a natural Reddit reply:",
    "Here's a Reddit reply:",
    "Here is a natural, helpful Reddit reply:",
    "Here is a natural Reddit reply:",
    "Here is a Reddit reply:",
    "Sure!",
    "Of course!",
    "Absolutely!",
    "Great question!",
    "Great point!",
    "I'd be happy to help",
    "I'd be happy to",
    "Happy to help!",
    "Hope this helps!",
    "Just my two cents",
    "tl;dr",
    "TL;DR",
)

# Sycophantic openers that signal "AI being agreeable". When found at the
# start of a reply, strip them and any trailing comma/period so the rest of
# the sentence becomes the new opener.
_SYCOPHANT_OPENERS = (
    "Totally get that feeling, but",
    "Totally get that feeling,",
    "Totally get that feeling.",
    "Totally get that feeling",
    "Totally get that,",
    "Totally get that.",
    "Totally get that",
    "Totally with you on this,",
    "Totally with you on this.",
    "Totally with you on this",
    "Totally with you,",
    "Totally with you.",
    "Totally with you",
    "Totally agree,",
    "Totally agree.",
    "Totally agree",
    "Totally feel that,",
    "Totally feel that.",
    "Totally feel that",
    "Totally,",
    "Totally.",
    "Yeah totally,",
    "Yeah, totally feeling that.",
    "Yeah totally feeling that.",
    "Yeah, totally feeling that,",
    "Yeah, totally,",
    "I feel you,",
    "I feel you.",
    "I feel that,",
    "I feel that.",
    "I get you,",
    "I get you.",
    "I hear you,",
    "I hear you.",
    "I get it,",
    "I get it.",
    "Same here,",
    "Same here.",
    "Same,",
    "Fair enough,",
    "Fair enough.",
    "Fair point,",
    "Fair point.",
    "Honestly,",
    "Honestly",
    "Oof,",
    "Oof.",
    "Yeah,",
    "Yeah",
    # Compound openers spotted in production output:
    "Lol, I feel you,",
    "Lol, I feel you.",
    "Lol I feel you,",
    "Lol I feel you.",
    "Lol, I feel that,",
    "Lol I feel that,",
    "Lol, I get you,",
    "Lol I get you,",
    "Totally fair point,",
    "Totally fair point.",
    "Totally fair point",
    "Fair point,",
    "Fair point.",
    "Yeah, I feel you,",
    "Yeah I feel you,",
    "Yeah, I get it,",
    "Yeah I get it,",
    "Yeah, fair point,",
    "Yeah fair point,",
    "Yeah, totally,",
    "Yeah totally,",
    "Yeah totally.",
    "Yep, totally,",
    "Yep totally,",
)


def _clean_ai_tells(text: str) -> str:
    s = _normalize_text(text.strip())
    # Strip surrounding quotes if the model wrapped the reply.
    if len(s) >= 2 and s[0] in {'"', "'"} and s[-1] == s[0]:
        s = s[1:-1].strip()

    # Normalize em/en/double-hyphen dashes to commas FIRST, so that opener
    # detection can match patterns like "Lol, I feel you—the rest..." which
    # would otherwise hide behind the dash.
    s = s.replace(" — ", ", ").replace(" – ", ", ")
    s = s.replace("—", ", ").replace("–", ", ")
    s = s.replace(" -- ", ", ").replace("--", ", ")

    # Drop common AI preambles.
    for prefix in _AI_PREFIXES:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].lstrip(" ,.!:;-")

    # Drop sycophantic openers ("Totally with you", "Honestly,", etc.).
    # Apply repeatedly in case multiple stack ("Honestly, totally agree,").
    # Leave whatever capitalization remains — lowercase opening is reddit-native.
    for _pass in range(3):
        before = s
        for opener in _SYCOPHANT_OPENERS:
            if s.lower().startswith(opener.lower()):
                s = s[len(opener):].lstrip(" ,.!:;-")
                break
        if s == before:
            break

    # Drop "Hope this helps!" and similar at the END.
    for tail in (
        "Hope this helps!",
        "Hope this helps.",
        "Hope that helps!",
        "Hope that helps.",
        "Good luck!",
        "Good luck.",
        "Cheers!",
        "Cheers.",
    ):
        if s.endswith(tail):
            s = s[: -len(tail)].rstrip()

    # Collapse double spaces / stray commas left by replacements.
    while "  " in s:
        s = s.replace("  ", " ")
    s = s.replace(" ,", ",").replace(",,", ",").strip(" ,")

    return s


def _normalize_text(text: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": ", ",
        "\u2013": ", ",
        "\u00a0": " ",
        "I?m": "I'm",
        "I?ve": "I've",
        "I?d": "I'd",
        "it?s": "it's",
        "that?s": "that's",
        "there?s": "there's",
        "you?re": "you're",
        "don?t": "don't",
        "doesn?t": "doesn't",
        "can?t": "can't",
        "isn?t": "isn't",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text


def _comment_allows_promo(comment: str) -> bool:
    lowered = comment.lower()
    return any(keyword in lowered for keyword in _PROMO_ALLOWED_KEYWORDS)


def _reply_is_acceptable(text: str, include_promo: bool, comment: str) -> bool:
    if not text or len(text) > settings.reply_max_chars:
        return False
    lowered = text.lower()
    if any(prefix.lower() in lowered[:80] for prefix in _AI_PREFIXES):
        return False
    if any(phrase in lowered for phrase in _PROMO_SALESY_PHRASES):
        return False
    if not include_promo and "sentx" in lowered:
        return False
    # When the reply was supposed to include the promo, REQUIRE it. Without
    # this check the model will frequently decide "natural fit" doesn't apply
    # and silently produce a non-promo reply that still gets the promo flag.
    if include_promo and "sentx" not in lowered:
        return False
    if any(marker in text for marker in ("```", "* ", "- ", "# ")):
        return False
    if _sentence_count(text) > 2:
        return False
    return True


def _sentence_count(text: str) -> int:
    parts = [part for part in re.split(r"[.!?]+(?:\s+|$)", text.strip()) if part.strip()]
    return max(1, len(parts)) if text.strip() else 0


def _enforce_reply_length(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = ""
    for sentence in sentences:
        candidate = f"{kept} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        kept = candidate
    if kept:
        return kept.rstrip(" ,")

    return text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.!?") or text[:max_chars].strip()


def _fallback_reply(comment: str) -> str:
    lowered = comment.lower()
    if "?" in comment:
        return "depends on the exact setup, but the missing detail is probably the constraint around how it gets used"
    if any(word in lowered for word in ("agent", "automation", "workflow", "tool")):
        return "the hard part is usually the handoff between the tool and the messy real workflow"
    return "the main thing missing here is the practical tradeoff, not the headline claim"


def process_glp(
    db: Session,
    limit: int = 30,
    scrape_run: ScrapeRun | None = None,
) -> dict:
    """GLP-specific scrape: fetch newthreads, fetch each thread page, run the
    same classify+reply pipeline as Reddit. Mirrors `process_subreddit()` but
    pulls from `glp_service` and tags every Reply with platform='glp'.
    """
    from app.services.glp_service import (  # local import to avoid Playwright import on startup
        fetch_topic_threads,
        fetch_thread,
        thread_to_items,
    )

    # GLP has no dedicated AI forum, so we scrape the configured tech topic(s)
    # (default Science/Technology) rather than the all-topics newthreads feed.
    # Each stub is tagged with its topic slug as `section`, and we carry that
    # onto the thread detail so saved posts/replies inherit it for
    # assigned_sections filtering.
    topics = settings.glp_topics or ["Science/Technology"]
    per_topic = max(1, limit // len(topics))
    stubs = []
    for topic in topics:
        payload = fetch_topic_threads(topic, limit=per_topic)
        stubs.extend(payload.get("thread_stubs") or [])

    stats = {"posts": 0, "comments": 0, "replies": 0}
    current_post: Post | None = None
    posts_by_url: dict[str, Post] = {}

    for stub in stubs:
        detail = fetch_thread(stub.thread_id)
        if detail is None:
            continue
        detail.section = stub.section  # propagate topic tag onto the thread
        for row in thread_to_items(detail):
            row_type = (row.get("dataType") or "").lower()
            if row_type == "post":
                current_post = save_post(db, "glp", row)
                posts_by_url[current_post.url] = current_post
                stats["posts"] += 1
                continue
            if row_type != "comment":
                continue
            comment_payload = {
                "text": row.get("text") or "",
                "post_url": row.get("post_url") or (current_post.url if current_post else ""),
                "comment_url": row.get("comment_url"),
                "author": row.get("author"),
                "upvotes": row.get("upvotes") or 0,
                "created_at": _parse_datetime(row.get("createdAt")) or datetime.utcnow(),
            }
            if not comment_payload["text"].strip():
                continue
            post = posts_by_url.get(comment_payload["post_url"]) or current_post
            if not post:
                continue
            comment = save_comment(db, post.id, comment_payload)
            stats["comments"] += 1
            if not classify_ai_relevance(comment_payload["text"]):
                continue
            include_promo = should_insert_promo()
            reply_text = generate_reply(comment.text, include_promo, platform="glp")
            # GLP runs full-auto by default: scrape → draft → APPROVED →
            # Playwright worker picks it up. Set GLP_AUTO_APPROVE=0 to revert
            # to manual-review (PENDING) mode.
            glp_status = "APPROVED" if settings.glp_auto_approve else "PENDING"
            reply = save_reply(
                db,
                comment_id=comment.id,
                reply_text=reply_text,
                is_ai_relevant=True,
                includes_promo=include_promo,
                platform="glp",
                status=glp_status,
            )
            if reply:
                stats["replies"] += 1
    return {**stats, "apify_run_id": None}


def process_chan(
    db: Session,
    boards: list[str] | None = None,
    threads_per_board: int | None = None,
    scrape_run: ScrapeRun | None = None,
) -> dict:
    """4chan scrape: pull catalogs for configured boards, fetch each thread's
    posts via the public JSON API, run the classify+reply pipeline.

    Mirrors `process_glp` but uses requests (no Playwright) for reading since
    4chan publishes thread state at https://a.4cdn.org/. Tags every reply
    with platform='chan'."""
    from app.services.chan_service import fetch_boards, fetch_thread, thread_to_items

    boards = boards or list(settings.chan_boards)
    threads_per_board = threads_per_board or settings.chan_threads_per_board

    stats = {"posts": 0, "comments": 0, "replies": 0}
    payload = fetch_boards(boards)
    stubs = payload.get("thread_stubs") or []

    # Bucket stubs by board and cap each board to threads_per_board so the LLM
    # budget per beat tick stays bounded.
    by_board: dict[str, list] = {}
    for stub in stubs:
        by_board.setdefault(stub.board, []).append(stub)
    capped: list = []
    for board in boards:
        capped.extend(by_board.get(board, [])[:threads_per_board])

    current_post: Post | None = None
    posts_by_url: dict[str, Post] = {}

    for stub in capped:
        detail = fetch_thread(stub.board, stub.thread_id)
        if detail is None:
            continue
        for row in thread_to_items(detail):
            row_type = (row.get("dataType") or "").lower()
            if row_type == "post":
                current_post = save_post(db, stub.board, row)
                posts_by_url[current_post.url] = current_post
                stats["posts"] += 1
                continue
            if row_type != "comment":
                continue
            comment_payload = {
                "text": row.get("text") or "",
                "post_url": row.get("post_url") or (current_post.url if current_post else ""),
                "comment_url": row.get("comment_url"),
                "author": row.get("author"),
                "upvotes": row.get("upvotes") or 0,
                "created_at": _parse_datetime(row.get("createdAt")) or datetime.utcnow(),
            }
            if not comment_payload["text"].strip():
                continue
            post = posts_by_url.get(comment_payload["post_url"]) or current_post
            if not post:
                continue
            comment = save_comment(db, post.id, comment_payload)
            stats["comments"] += 1
            if not classify_ai_relevance(comment_payload["text"]):
                continue
            include_promo = should_insert_promo()
            reply_text = generate_reply(comment.text, include_promo, platform="chan")
            chan_status = "APPROVED" if settings.chan_auto_approve else "PENDING"
            reply = save_reply(
                db,
                comment_id=comment.id,
                reply_text=reply_text,
                is_ai_relevant=True,
                includes_promo=include_promo,
                platform="chan",
                status=chan_status,
            )
            if reply:
                stats["replies"] += 1
    return {**stats, "apify_run_id": None}


def process_subreddit(
    db: Session,
    subreddit: str,
    limit: int = 50,
    scrape_run: ScrapeRun | None = None,
) -> dict:
    subreddit = subreddit.strip().removeprefix("r/")
    apify_payload = fetch_subreddit(subreddit, limit=limit)
    rows = apify_payload["items"]
    stats = {"posts": 0, "comments": 0, "replies": 0}
    current_post: Post | None = None
    posts_by_url: dict[str, Post] = {}

    if scrape_run:
        scrape_run.apify_run_id = apify_payload.get("apify_run_id")
        db.add(scrape_run)
        db.commit()
        db.refresh(scrape_run)

    for row in rows:
        row_type = (row.get("dataType") or row.get("type") or "").lower()
        if row_type == "post":
            current_post = save_post(db, subreddit, row)
            posts_by_url[current_post.url] = current_post
            stats["posts"] += 1
            continue

        if row_type != "comment":
            continue

        comment_payload = normalize_comment(
            row,
            fallback_post_url=current_post.url if current_post else None,
        )
        if not comment_payload["text"].strip():
            continue

        post = resolve_post_for_comment(
            db,
            subreddit=subreddit,
            payload=comment_payload,
            posts_by_url=posts_by_url,
            fallback_post=current_post,
        )
        if not post:
            continue

        comment = save_comment(db, post.id, comment_payload)
        stats["comments"] += 1
        if not classify_ai_relevance(comment_payload["text"]):
            continue

        include_promo = should_insert_promo()
        reply_text = generate_reply(comment.text, include_promo)
        reply = save_reply(
            db,
            comment_id=comment.id,
            reply_text=reply_text,
            is_ai_relevant=True,
            includes_promo=include_promo,
        )
        if reply:
            stats["replies"] += 1

    return {
        **stats,
        "apify_run_id": apify_payload.get("apify_run_id"),
    }


def save_post(db: Session, subreddit: str, raw_post: dict) -> Post:
    url = absolute_reddit_url(raw_post.get("url") or raw_post.get("postUrl") or raw_post.get("permalink"))
    if not url:
        raise ValueError("Post is missing a URL.")

    community_name = raw_post.get("subreddit") or raw_post.get("communityName") or f"r/{subreddit}"
    normalized_subreddit = community_name.removeprefix("r/") if community_name else subreddit
    existing = db.scalar(select(Post).where(Post.url == url))
    if existing:
        existing.subreddit = normalized_subreddit
        existing.title = raw_post.get("title") or existing.title
        existing.body = raw_post.get("selfText") or raw_post.get("body") or existing.body
        existing.upvotes = raw_post.get("score") or raw_post.get("upVotes") or raw_post.get("upvotes") or existing.upvotes
        existing.number_of_comments = (
            raw_post.get("numComments")
            or raw_post.get("numberOfComments")
            or raw_post.get("number_of_comments")
            or existing.number_of_comments
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    post = Post(
        subreddit=normalized_subreddit,
        title=raw_post.get("title") or "Untitled Post",
        body=raw_post.get("selfText") or raw_post.get("body"),
        url=url,
        upvotes=raw_post.get("score") or raw_post.get("upVotes") or raw_post.get("upvotes") or 0,
        number_of_comments=(
            raw_post.get("numComments")
            or raw_post.get("numberOfComments")
            or raw_post.get("number_of_comments")
            or 0
        ),
        created_at=_parse_datetime(raw_post.get("createdAt")) or datetime.utcnow(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def save_comment(db: Session, post_id: int, payload: dict) -> Comment:
    stmt = select(Comment).where(
        Comment.post_id == post_id,
        Comment.text == payload["text"],
        Comment.comment_url == payload["comment_url"],
    )
    existing = db.scalar(stmt)
    if existing:
        existing.author = payload["author"]
        existing.post_url = payload["post_url"]
        existing.upvotes = payload["upvotes"]
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    comment = Comment(
        post_id=post_id,
        text=payload["text"],
        comment_url=payload["comment_url"],
        post_url=payload["post_url"],
        author=payload["author"],
        upvotes=payload["upvotes"],
        created_at=payload["created_at"] or datetime.utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def generate_replies_for_unreplied(
    db: Session,
    subreddit: str,
    limit: int = 30,
    max_comment_created_at: datetime | None = None,
    promo_ratio_override: float | None = None,
    skip_judge: bool = False,
) -> dict:
    """Run the LLM on existing scraped Comments that don't have an associated
    Reply yet. Skips Apify entirely — useful when fresh scraping is blocked
    (e.g. Apify quota exhausted) but the DB has plenty of unprocessed
    comments to generate replies for.

    - max_comment_created_at: only consider comments created strictly BEFORE
      this datetime. Lets us target the pre-fix-era pool without re-replying
      to recently-scraped comments.
    - promo_ratio_override: override the global REPLY_PROMO_RATIO for this
      batch (e.g. 0.8 for a promo-biased regeneration run)."""
    normalized = subreddit.strip().removeprefix("r/")

    # Per-sub PENDING cap: if a sub already has >= cap PENDING replies, skip
    # this job entirely. Prevents runaway single-sub bursts that swamp the
    # live queue. Configurable via env (default 100).
    cap = int(os.getenv("PER_SUB_PENDING_CAP", "100"))
    existing_pending = (
        db.scalar(
            select(func.count(Reply.id))
            .join(Comment, Reply.comment_id == Comment.id)
            .join(Post, Comment.post_id == Post.id)
            .where(Reply.status == "PENDING", Post.subreddit.ilike(normalized))
        )
        or 0
    )
    if existing_pending >= cap:
        return {
            "considered": 0,
            "ai_relevant": 0,
            "replies_created": 0,
            "failed": 0,
            "skipped": "per_sub_pending_cap_reached",
            "existing_pending": existing_pending,
            "cap": cap,
        }

    stmt = (
        select(Comment)
        .join(Comment.post)
        .outerjoin(Reply, Reply.comment_id == Comment.id)
        .where(
            Reply.id == None,  # noqa: E711
            Post.subreddit.ilike(normalized),
        )
    )
    if max_comment_created_at is not None:
        stmt = stmt.where(Comment.created_at < max_comment_created_at)
    stmt = (
        stmt.order_by(Comment.upvotes.desc(), Comment.id.desc())
        .limit(limit * 4)  # Pull a wider pool — many will be filtered out as non-AI-relevant.
    )
    comments = list(db.scalars(stmt).all())
    stats = {"considered": 0, "ai_relevant": 0, "replies_created": 0, "failed": 0}
    for comment in comments:
        if stats["replies_created"] >= limit:
            break
        if not comment.text or not comment.text.strip():
            continue
        stats["considered"] += 1
        try:
            if not classify_ai_relevance(comment.text):
                continue
            stats["ai_relevant"] += 1
            if promo_ratio_override is not None:
                include_promo = random.random() < promo_ratio_override
            else:
                include_promo = should_insert_promo()
            reply_text = generate_reply(comment.text, include_promo, skip_judge=skip_judge)
            if not reply_text:
                stats["failed"] += 1
                continue
            saved = save_reply(
                db,
                comment_id=comment.id,
                reply_text=reply_text,
                is_ai_relevant=True,
                includes_promo=include_promo,
            )
            if saved is not None:
                stats["replies_created"] += 1
        except Exception:  # noqa: BLE001
            stats["failed"] += 1
            continue
    return stats


def _promo_fits_naturally(comment: str, reply: str) -> bool:
    """LLM judge: would a real Reddit user mentioning sentx.ai in this reply
    look organic, or like a forced promo? Returns True only when the model
    answers YES with high confidence. Used to filter awkward fits when the
    strict 'MUST mention sentx.ai' prompt produces something that doesn't
    belong on the source comment's topic.

    Cheap call: <30 tokens out, deterministic-ish prompt.
    """
    judge_prompt = (
        "You are checking whether a Reddit reply ACTUALLY RECOMMENDS the AI "
        "tool 'sentx.ai' in a way that fits the original comment's topic.\n\n"
        f"Original comment: {comment.strip()[:500]}\n\n"
        f"Reply (must mention sentx.ai): {reply.strip()[:400]}\n\n"
        "Answer YES only if BOTH are true:\n"
        "  (a) the mention is a clear recommendation, endorsement, or personal-use "
        "vouch for sentx.ai (NOT just naming it as something tracked, observed, "
        "or referenced).\n"
        "  (b) the topic plausibly fits an AI/dev/automation tool — i.e. the "
        "recommendation would not look like a random plug to a Reddit reader.\n\n"
        "Answer NO if the reply just name-drops sentx.ai without recommending it, "
        "if the topic is unrelated to AI/dev/automation, or if the mention feels "
        "shoehorned.\n\n"
        "Reply with ONE WORD: YES or NO."
    )
    try:
        verdict = deepseek_call(judge_prompt).strip().upper()
    except Exception:  # noqa: BLE001
        # If the judge fails, fall back to "fits" — better to keep a possibly
        # ok reply than to drop a working one because of a transient error.
        return True
    return verdict.startswith("YES")


def reply_text_has_promo(text: str) -> bool:
    """Source of truth for whether a reply actually mentions our product.
    The `include_promo` request is just an invitation — the model can skip
    it. So `includes_promo` must be derived from the final text, not from
    the prompt flag, to keep dashboard counts honest."""
    return "sentx" in (text or "").lower()


def save_reply(
    db: Session,
    comment_id: int,
    reply_text: str,
    is_ai_relevant: bool,
    includes_promo: bool,
    status: str = "PENDING",
    platform: str = "reddit",
) -> Reply | None:
    existing = db.scalar(select(Reply).where(Reply.comment_id == comment_id))
    if existing:
        return None

    targets: dict = {}
    platform_targets: dict = {}
    comment = db.get(Comment, comment_id)
    if comment is not None:
        post_subreddit = comment.post.subreddit if comment.post is not None else None
        if platform == "glp":
            from app.services.glp_targets import parse_glp_url  # local import
            primary_url = comment.comment_url or comment.post_url
            ref = parse_glp_url(primary_url) if primary_url else None
            platform_targets = {
                "target_url": primary_url,
                "target_type": "comment" if comment.comment_url else "post",
                "platform_post_id": ref.thread_id if ref else None,
                "platform_comment_id": ref.post_id if ref else None,
                "platform_section": post_subreddit,
            }
        elif platform == "chan":
            from app.services.chan_targets import parse_chan_url  # local import
            primary_url = comment.comment_url or comment.post_url
            ref = parse_chan_url(primary_url) if primary_url else None
            platform_targets = {
                "target_url": primary_url,
                "target_type": "comment" if comment.comment_url else "post",
                "platform_post_id": ref.thread_id if ref else None,
                "platform_comment_id": ref.post_id if ref else None,
                # `subreddit` field already holds the board (e.g. "g") via save_post.
                "platform_section": post_subreddit,
            }
        else:
            targets = derive_reply_targets(
                comment_url=comment.comment_url,
                post_url=comment.post_url,
                subreddit=post_subreddit,
            )

    # Override the requested flag with the truth from the generated text.
    actual_promo = reply_text_has_promo(reply_text)

    reply = Reply(
        comment_id=comment_id,
        reply_text=reply_text,
        is_ai_relevant=is_ai_relevant,
        includes_promo=actual_promo,
        status=status,
        platform=platform,
        target_url=targets.get("target_url") or platform_targets.get("target_url"),
        target_type=targets.get("target_type") or platform_targets.get("target_type"),
        reddit_post_id=targets.get("reddit_post_id"),
        reddit_comment_id=targets.get("reddit_comment_id"),
        subreddit=targets.get("subreddit"),
        platform_post_id=platform_targets.get("platform_post_id"),
        platform_comment_id=platform_targets.get("platform_comment_id"),
        platform_section=platform_targets.get("platform_section"),
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


def resolve_post_for_comment(
    db: Session,
    subreddit: str,
    payload: dict,
    posts_by_url: dict[str, Post],
    fallback_post: Post | None,
) -> Post | None:
    post_url = payload.get("post_url")
    if post_url and post_url in posts_by_url:
        return posts_by_url[post_url]

    if post_url:
        existing = db.scalar(select(Post).where(Post.url == post_url))
        if existing:
            posts_by_url[post_url] = existing
            return existing

        placeholder = Post(
            subreddit=subreddit.removeprefix("r/"),
            title="Untitled Post",
            url=post_url,
            created_at=datetime.utcnow(),
        )
        db.add(placeholder)
        db.commit()
        db.refresh(placeholder)
        posts_by_url[post_url] = placeholder
        return placeholder

    return fallback_post


def ensure_default_tracked_subreddits(db: Session) -> None:
    existing_names = {
        item.name.lower() for item in db.scalars(select(TrackedSubreddit)).all()
    }
    created = False
    for name in DEFAULT_TRACKED_SUBREDDITS:
        if name.lower() in existing_names:
            continue
        db.add(TrackedSubreddit(name=name))
        created = True
    if created:
        db.commit()


def derive_post_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(absolute_reddit_url(url))
    parts = [part for part in parsed.path.split("/") if part]
    try:
        comments_idx = parts.index("comments")
    except ValueError:
        return url

    if len(parts) < comments_idx + 3:
        return url

    post_path = "/" + "/".join(parts[: comments_idx + 3]) + "/"
    return f"{parsed.scheme}://{parsed.netloc}{post_path}"


def absolute_reddit_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.reddit.com{url}"
    return url


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
