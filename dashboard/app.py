import math
import os
from collections import Counter

import requests
import streamlit as st

# BACKEND_BASE_URL lets the dashboard run identically inside Docker Compose
# (default http://backend:8000) and on a developer host pointed at a remote
# backend (e.g. http://localhost:8000).
API = os.getenv("BACKEND_BASE_URL", "http://backend:8000").rstrip("/")


def api_get(path: str, **kwargs):
    response = requests.get(f"{API}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def api_post(path: str, **kwargs):
    response = requests.post(f"{API}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def api_patch(path: str, **kwargs):
    response = requests.patch(f"{API}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def api_delete(path: str, **kwargs):
    response = requests.delete(f"{API}{path}", timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


def load_tracked_subreddits():
    return api_get("/tracked-subreddits")


def load_subreddit_content(subreddit: str, page: int, page_size: int, comment_limit: int):
    return api_get(
        f"/subreddits/{subreddit}/content",
        params={"page": page, "page_size": page_size, "comment_limit": comment_limit},
    )


def load_replies(status: str, limit: int, subreddit: str | None = None):
    params = {"status": status, "limit": limit}
    if subreddit and subreddit != "All":
        params["subreddit"] = subreddit
    return api_get("/replies", params=params)


def load_scrape_runs(page: int, page_size: int, subreddit: str | None = None):
    params = {"page": page, "page_size": page_size}
    if subreddit and subreddit != "All":
        params["subreddit"] = subreddit
    return api_get("/scrape-runs", params=params)


def load_opportunities(subreddit: str, page: int, page_size: int, reply_limit: int):
    return api_get(
        f"/subreddits/{subreddit}/opportunities",
        params={"page": page, "page_size": page_size, "reply_limit": reply_limit},
    )


def safe_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\u00a0", " ").strip()
    try:
        repaired = text.encode("latin1").decode("utf-8")
        if repaired.count("ï¿½") <= text.count("ï¿½"):
            text = repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text


def reply_value(reply: dict) -> int:
    return (
        max(reply["post_upvotes"], 0) * 3
        + max(reply["comment_upvotes"], 0) * 4
        + max(reply["post_comment_count"], 0)
    )


def total_pages(total_items: int, page_size: int) -> int:
    return max(1, math.ceil(total_items / page_size)) if page_size else 1


def set_page(key: str, value: int):
    st.session_state[key] = max(1, value)


def render_pagination(key: str, page: int, total_items: int, page_size: int, label: str):
    pages = total_pages(total_items, page_size)
    col1, col2, col3 = st.columns([1, 2, 1])
    if col1.button("Previous", key=f"{key}_prev", use_container_width=True, disabled=page <= 1):
        set_page(key, page - 1)
        st.rerun()
    col2.markdown(
        f"<div class='pager-label'>{label}: page {page} of {pages} <span>{total_items} total</span></div>",
        unsafe_allow_html=True,
    )
    if col3.button("Next", key=f"{key}_next", use_container_width=True, disabled=page >= pages):
        set_page(key, page + 1)
        st.rerun()


def mark_reply_done(reply_id: int):
    api_patch(f"/replies/{reply_id}", json={"status": "DONE"})


def approve_reply(reply_id: int):
    api_patch(f"/replies/{reply_id}", json={"status": "APPROVED"})


def load_posting_queue(status: str, limit: int = 200):
    return api_get("/replies", params={"status": status, "limit": limit})


def load_worker_summary():
    try:
        return api_get("/worker/queue")
    except requests.RequestException:
        return {"counts": {}}


def render_reply_column(title: str, replies: list[dict], empty_message: str, column_key: str):
    st.markdown(f"<div class='split-title'>{title}</div>", unsafe_allow_html=True)
    if not replies:
        st.info(empty_message)
        return
    for reply in replies:
        st.markdown("<div class='reply-card'>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='reply-meta'>{reply['comment_upvotes']} comment upvotes | score {reply['value_score']} | {safe_text(reply['comment_author'] or 'unknown author')}</div>",
            unsafe_allow_html=True,
        )
        st.write(safe_text(reply["comment_text"]))
        if reply["comment_url"]:
            st.markdown(f"[Open Comment]({reply['comment_url']})")
        st.caption("Suggested reply")
        st.code(safe_text(reply["reply_text"]))
        approve_col, done_col, meta_col = st.columns([1.1, 1.1, 3.4])
        if approve_col.button(
            "Approve to Post",
            key=f"{column_key}_approve_{reply['reply_id']}",
            use_container_width=True,
        ):
            approve_reply(reply["reply_id"])
            st.rerun()
        if done_col.button("Mark Done", key=f"{column_key}_done_{reply['reply_id']}", use_container_width=True):
            mark_reply_done(reply["reply_id"])
            st.rerun()
        meta_col.markdown(
            (
                f"<div class='reply-action-note'>Drafted {reply['created_at']} | "
                f"{'Can mention sentx.ai' if reply['includes_promo'] else 'Normal reply'}</div>"
            ),
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


st.set_page_config(page_title="Reddit Reply Dashboard", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(251, 146, 60, 0.18), transparent 22%),
            radial-gradient(circle at 85% 0%, rgba(45, 212, 191, 0.12), transparent 20%),
            radial-gradient(circle at 50% 100%, rgba(59, 130, 246, 0.08), transparent 28%),
            linear-gradient(180deg, #08101c 0%, #101826 44%, #151b2f 100%);
    }
    .block-container {
        max-width: 1520px;
        padding-top: 1.1rem;
        padding-bottom: 2rem;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    .hero {
        padding: 1.2rem 1.3rem;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 26px;
        background:
            radial-gradient(circle at 88% 18%, rgba(251,146,60,0.26), transparent 20%),
            radial-gradient(circle at 12% 0%, rgba(45,212,191,0.16), transparent 26%),
            linear-gradient(135deg, rgba(10,16,29,0.98), rgba(23,31,52,0.94));
        box-shadow: 0 24px 52px rgba(0,0,0,0.26);
        margin-bottom: 1.1rem;
        position: relative;
        overflow: hidden;
    }
    .hero:after {
        content: "";
        position: absolute;
        inset: auto -10% -35% 30%;
        height: 180px;
        background: linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0));
        transform: rotate(-7deg);
    }
    .hero-grid {
        display: grid;
        grid-template-columns: 1.8fr 1fr;
        gap: 1rem;
        align-items: start;
    }
    .hero h1 {
        margin: 0;
        font-size: 2.3rem;
        line-height: 1;
    }
    .hero p {
        margin: 0.65rem 0 0;
        color: #cbd5e1;
        max-width: 800px;
        font-size: 0.98rem;
    }
    .hero-stack {
        display: grid;
        gap: 0.6rem;
        position: relative;
        z-index: 1;
    }
    .hero-pill, .hero-stat {
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.08);
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.68), rgba(15, 23, 42, 0.42));
        padding: 0.8rem 0.9rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .hero-stat strong {
        display: block;
        font-size: 1.35rem;
        margin-top: 0.2rem;
    }
    .panel {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(9, 17, 31, 0.82), rgba(9, 17, 31, 0.72));
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(14px);
        box-shadow: 0 18px 40px rgba(0,0,0,0.18);
    }
    .metric-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        background:
            radial-gradient(circle at top right, rgba(59,130,246,0.14), transparent 26%),
            linear-gradient(180deg, rgba(15,23,42,0.94), rgba(15,23,42,0.74));
        padding: 0.95rem 1rem;
        box-shadow: 0 10px 26px rgba(0,0,0,0.14);
    }
    .metric-label {
        font-size: 0.76rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        margin-top: 0.18rem;
    }
    .section-note {
        color: #94a3b8;
        font-size: 0.92rem;
        margin-top: -0.2rem;
        margin-bottom: 0.85rem;
    }
    .subreddit-chip {
        display: inline-block;
        padding: 0.34rem 0.68rem;
        border-radius: 999px;
        background: rgba(251,146,60,0.14);
        color: #fdba74;
        font-weight: 600;
        margin-bottom: 0.65rem;
    }
    .post-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 22px;
        background:
            radial-gradient(circle at top right, rgba(45,212,191,0.08), transparent 26%),
            linear-gradient(180deg, rgba(15,23,42,0.94), rgba(17,24,39,0.84));
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 14px 34px rgba(0,0,0,0.18);
    }
    .post-topline {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        align-items: flex-start;
        margin-bottom: 0.45rem;
    }
    .post-title {
        font-size: 1.15rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .score-pill {
        padding: 0.36rem 0.62rem;
        border-radius: 999px;
        background: rgba(56,189,248,0.14);
        color: #bae6fd;
        font-size: 0.82rem;
        white-space: nowrap;
    }
    .post-meta, .reply-meta, .history-meta {
        color: #94a3b8;
        font-size: 0.84rem;
        margin-bottom: 0.55rem;
    }
    .comment-chip {
        border-left: 3px solid rgba(56,189,248,0.45);
        background: linear-gradient(180deg, rgba(15,23,42,0.58), rgba(15,23,42,0.42));
        padding: 0.7rem 0.8rem;
        border-radius: 12px;
        margin: 0.55rem 0;
    }
    .history-card, .reply-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        background:
            radial-gradient(circle at top right, rgba(251,146,60,0.08), transparent 28%),
            linear-gradient(180deg, rgba(15, 23, 42, 0.78), rgba(15, 23, 42, 0.62));
        padding: 0.9rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 10px 26px rgba(0,0,0,0.14);
    }
    .split-title {
        color: #e2e8f0;
        font-size: 0.92rem;
        font-weight: 700;
        margin-bottom: 0.55rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .promote-tag, .normal-tag, .status-tag {
        display: inline-block;
        padding: 0.28rem 0.56rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        margin-right: 0.4rem;
    }
    .promote-tag {
        background: rgba(249,115,22,0.16);
        color: #fdba74;
    }
    .normal-tag {
        background: rgba(34,197,94,0.14);
        color: #86efac;
    }
    .status-tag {
        background: rgba(148,163,184,0.14);
        color: #cbd5e1;
    }
    .pager-label {
        text-align: center;
        color: #cbd5e1;
        padding-top: 0.45rem;
        font-size: 0.94rem;
    }
    .pager-label span {
        color: #94a3b8;
        margin-left: 0.35rem;
    }
    .reply-action-note {
        color: #94a3b8;
        font-size: 0.8rem;
        padding-top: 0.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tracked_subreddits = load_tracked_subreddits()
tracked_names = [item["name"] for item in tracked_subreddits]

if "selected_subreddit" not in st.session_state:
    st.session_state.selected_subreddit = tracked_names[0] if tracked_names else None

if tracked_names and st.session_state.selected_subreddit not in tracked_names:
    st.session_state.selected_subreddit = tracked_names[0]

for key in ("feed_page", "history_page", "opportunity_page"):
    if key not in st.session_state:
        st.session_state[key] = 1

selected_subreddit = st.session_state.selected_subreddit
feed_page = st.session_state.feed_page
history_page = st.session_state.history_page
opportunity_page = st.session_state.opportunity_page

selected_content = (
    load_subreddit_content(selected_subreddit, feed_page, 4, 4) if selected_subreddit else None
)
opportunities = (
    load_opportunities(selected_subreddit, opportunity_page, 3, 3) if selected_subreddit else None
)
pending_replies = load_replies("PENDING", 120, selected_subreddit)
done_replies = load_replies("DONE", 30, selected_subreddit)
recent_scrape_runs = load_scrape_runs(history_page, 6, selected_subreddit)
ranked_pending = sorted(pending_replies, key=reply_value, reverse=True)

draft_counts = Counter(item["subreddit"] for item in pending_replies)
top_sources = " | ".join(
    f"r/{name}: {count}" for name, count in draft_counts.most_common(6)
) if draft_counts else "No pending drafts yet"

hero_total_opportunities = len(ranked_pending)
hero_promotable = sum(1 for item in ranked_pending if item["includes_promo"])

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-grid">
        <div>
          <h1>Reddit Reply Command Center</h1>
          <p>Browse subreddit posts like a scouting board, inspect scrape history, and split each subreddit into promotable SentX opportunities versus normal high-quality reply targets.</p>
        </div>
        <div class="hero-stack">
          <div class="hero-pill">Selected subreddit: <strong>r/{selected_subreddit or "none"}</strong></div>
          <div class="hero-stat">Open opportunities<strong>{hero_total_opportunities}</strong></div>
          <div class="hero-stat">Promotable candidates<strong>{hero_promotable}</strong></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

sidebar_col, main_col = st.columns([0.95, 2.45], gap="large")

with sidebar_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Controls")
    new_subreddit = st.text_input("Add subreddit", placeholder="OpenAI")
    if st.button("Add Subreddit", use_container_width=True) and new_subreddit.strip():
        api_post("/tracked-subreddits", json={"name": new_subreddit.strip()})
        st.rerun()

    scrape_limit = st.number_input("Scrape limit", min_value=1, max_value=500, value=5)
    action_cols = st.columns(2)
    if action_cols[0].button("Scrape All", use_container_width=True):
        api_post("/tracked-subreddits/run", params={"limit": int(scrape_limit)})
        st.success("Queued tracked subreddits")
        st.rerun()
    if selected_subreddit and action_cols[1].button("Scrape Selected", use_container_width=True):
        api_post("/fetch", json={"subreddits": [selected_subreddit], "limit": int(scrape_limit)})
        st.success(f"Queued r/{selected_subreddit}")
        st.rerun()

    st.caption("Automatic scraping runs every 6 hours.")
    st.divider()
    st.subheader("Tracked Subreddits")
    search_term = st.text_input("Filter", placeholder="Search tracked names")
    filtered = [
        item for item in tracked_subreddits
        if search_term.lower().strip() in item["name"].lower()
    ]
    for item in filtered:
        row_select, row_delete = st.columns([4, 1.4])
        active = item["name"] == selected_subreddit
        if row_select.button(
            f"r/{item['name']}",
            key=f"select_{item['id']}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state.selected_subreddit = item["name"]
            st.session_state.feed_page = 1
            st.session_state.history_page = 1
            st.session_state.opportunity_page = 1
            st.rerun()
        if row_delete.button("Delete", key=f"delete_{item['id']}", use_container_width=True):
            api_delete(f"/tracked-subreddits/{item['id']}")
            if selected_subreddit == item["name"]:
                st.session_state.selected_subreddit = None
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with main_col:
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.markdown(
        f'<div class="metric-card"><div class="metric-label">Tracked</div><div class="metric-value">{len(tracked_subreddits)}</div></div>',
        unsafe_allow_html=True,
    )
    metric2.markdown(
        f'<div class="metric-card"><div class="metric-label">Pending Drafts</div><div class="metric-value">{len(pending_replies)}</div></div>',
        unsafe_allow_html=True,
    )
    metric3.markdown(
        f'<div class="metric-card"><div class="metric-label">Promotable</div><div class="metric-value">{hero_promotable}</div></div>',
        unsafe_allow_html=True,
    )
    metric4.markdown(
        f'<div class="metric-card"><div class="metric-label">Stored Posts</div><div class="metric-value">{selected_content["total_posts"] if selected_content else 0}</div></div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "Feed",
        "Opportunities",
        "Scrape History",
        "Done Replies",
        "Posting Queue",
    ])
    feed_tab, opportunities_tab, history_tab, done_tab, posting_tab = tabs

    with feed_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Reddit Post Cards")
        st.markdown(
            f'<div class="section-note">Reddit-style scouting cards for <strong>r/{selected_subreddit}</strong>. Click through pages instead of loading one long feed.</div>'
            if selected_subreddit else '<div class="section-note">Select a subreddit to inspect its posts and comments.</div>',
            unsafe_allow_html=True,
        )
        if selected_subreddit:
            st.markdown(f'<div class="subreddit-chip">r/{selected_subreddit}</div>', unsafe_allow_html=True)

        if selected_content and selected_content["posts"]:
            for post in selected_content["posts"]:
                st.markdown("<div class='post-card'>", unsafe_allow_html=True)
                st.markdown(
                    (
                        "<div class='post-topline'>"
                        f"<div class='post-title'>{safe_text(post['title'])}</div>"
                        f"<div class='score-pill'>{post['upvotes']} upvotes</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='post-meta'>{post['number_of_comments']} comments | created {post['created_at']}</div>",
                    unsafe_allow_html=True,
                )
                body = safe_text(post.get("body"))
                if body:
                    st.write(body[:900])
                st.markdown(f"[Open Thread]({post['url']})")
                if post["top_comments"]:
                    st.caption("Top comments")
                    for comment in post["top_comments"]:
                        st.markdown("<div class='comment-chip'>", unsafe_allow_html=True)
                        st.markdown(
                            f"<div class='reply-meta'>{comment['upvotes']} upvotes | {safe_text(comment['author'] or 'unknown author')}</div>",
                            unsafe_allow_html=True,
                        )
                        st.write(safe_text(comment["text"]))
                        if comment["comment_url"]:
                            st.markdown(f"[Open Comment]({comment['comment_url']})")
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.info("No comments stored yet for this post.")
                st.markdown("</div>", unsafe_allow_html=True)
            render_pagination(
                "feed_page",
                selected_content["page"],
                selected_content["total_posts"],
                selected_content["page_size"],
                "Feed",
            )
        else:
            st.info("No scraped content is stored yet for this subreddit.")
        st.markdown("</div>", unsafe_allow_html=True)

    with opportunities_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Potential Comments And Replies")
        st.markdown(
            f'<div class="section-note">Grouped by post for <strong>r/{selected_subreddit}</strong>. Each card splits SentX-promotable opportunities from normal high-quality reply targets. Top source mix: {top_sources}</div>',
            unsafe_allow_html=True,
        )
        if opportunities and opportunities["posts"]:
            for post in opportunities["posts"]:
                st.markdown("<div class='post-card'>", unsafe_allow_html=True)
                st.markdown(
                    (
                        "<div class='post-topline'>"
                        f"<div class='post-title'>{safe_text(post['post_title'])}</div>"
                        f"<div class='score-pill'>opportunity score {post['opportunity_score']}</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    (
                        f"<span class='promote-tag'>Promotable {post['promotable_count']}</span>"
                        f"<span class='normal-tag'>Normal {post['normal_count']}</span>"
                        f"<span class='status-tag'>{post['post_upvotes']} upvotes | {post['post_comment_count']} comments</span>"
                    ),
                    unsafe_allow_html=True,
                )
                post_body = safe_text(post.get("post_body"))
                if post_body:
                    st.write(post_body[:700])
                st.markdown(f"[Open Thread]({post['post_url']})")
                left, right = st.columns(2, gap="large")
                with left:
                    render_reply_column(
                        "Can Promote sentx.ai",
                        post["promotable_replies"],
                        "No promotable replies queued for this post yet.",
                        f"promo_{post['post_id']}",
                    )
                with right:
                    render_reply_column(
                        "Normal Good Replies",
                        post["normal_replies"],
                        "No normal replies queued for this post yet.",
                        f"normal_{post['post_id']}",
                    )
                st.markdown("</div>", unsafe_allow_html=True)
            render_pagination(
                "opportunity_page",
                opportunities["page"],
                opportunities["total_posts"],
                opportunities["page_size"],
                "Opportunities",
            )
        else:
            st.info("No grouped reply opportunities are available for this subreddit yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with history_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Scrape History")
        st.markdown(
            '<div class="section-note">Audit trail for scheduled and manual runs, with pagination so the history stays readable.</div>',
            unsafe_allow_html=True,
        )
        history_runs = recent_scrape_runs["runs"] if recent_scrape_runs else []
        if history_runs:
            for run in history_runs:
                apify_ref = run["apify_run_id"] or "pending"
                finished = run["finished_at"] or "running"
                st.markdown("<div class='history-card'>", unsafe_allow_html=True)
                st.markdown(
                    (
                        f"**r/{run['subreddit']}** "
                        f"<span class='status-tag'>{run['source']}</span>"
                        f"<span class='status-tag'>{run['status']}</span>"
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='history-meta'>limit {run['limit']} | posts {run['posts_count']} | comments {run['comments_count']} | replies {run['replies_count']} | Apify {apify_ref}</div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Started {run['created_at']} | Finished {finished} | Trigger {run['triggered_by'] or 'n/a'}")
                if run["error_message"]:
                    st.error(run["error_message"])
                st.markdown("</div>", unsafe_allow_html=True)
            render_pagination(
                "history_page",
                recent_scrape_runs["page"],
                recent_scrape_runs["total_runs"],
                recent_scrape_runs["page_size"],
                "History",
            )
        else:
            st.info("No scrape activity recorded yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with done_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Done Replies")
        st.markdown(
            '<div class="section-note">Completed replies for the current subreddit scope.</div>',
            unsafe_allow_html=True,
        )
        if done_replies:
            for item in done_replies:
                st.markdown("<div class='reply-card'>", unsafe_allow_html=True)
                st.markdown(f"### {safe_text(item['post_title'])}")
                st.markdown(
                    f"<div class='reply-meta'>r/{item['subreddit']} | post {item['post_upvotes']} upvotes | comment {item['comment_upvotes']} upvotes</div>",
                    unsafe_allow_html=True,
                )
                st.write("Comment")
                st.write(safe_text(item["comment_text"]))
                st.write("Reply")
                st.code(safe_text(item["reply_text"]))
                if item["comment_url"]:
                    st.markdown(f"[Open Comment]({item['comment_url']})")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No done replies yet for the current subreddit scope.")
        st.markdown("</div>", unsafe_allow_html=True)

    with posting_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Posting Queue")
        st.markdown(
            '<div class="section-note">Approved drafts are claimed by the Playwright worker and posted to Reddit. Failed jobs are requeued automatically and can be retried here.</div>',
            unsafe_allow_html=True,
        )

        worker_counts = load_worker_summary().get("counts", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(
            f'<div class="metric-card"><div class="metric-label">Approved</div><div class="metric-value">{worker_counts.get("APPROVED", 0)}</div></div>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f'<div class="metric-card"><div class="metric-label">Posting</div><div class="metric-value">{worker_counts.get("POSTING", 0)}</div></div>',
            unsafe_allow_html=True,
        )
        c3.markdown(
            f'<div class="metric-card"><div class="metric-label">Posted</div><div class="metric-value">{worker_counts.get("POSTED", 0)}</div></div>',
            unsafe_allow_html=True,
        )
        c4.markdown(
            f'<div class="metric-card"><div class="metric-label">Failed</div><div class="metric-value">{worker_counts.get("FAILED", 0)}</div></div>',
            unsafe_allow_html=True,
        )

        for status_label, status_value in (
            ("Approved (waiting for worker)", "APPROVED"),
            ("Currently Posting", "POSTING"),
            ("Failed", "FAILED"),
            ("Recently Posted", "POSTED"),
        ):
            try:
                items = load_posting_queue(status_value, limit=50)
            except requests.RequestException as exc:
                st.error(f"Could not load {status_label}: {exc}")
                continue

            st.markdown(f"#### {status_label} ({len(items)})")
            if not items:
                st.caption("Nothing here yet.")
                continue

            for item in items:
                st.markdown("<div class='reply-card'>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='reply-meta'>r/{item['subreddit']} | reply #{item['reply_id']} | attempts {item.get('posting_attempts', 0)} | {item['status']}</div>",
                    unsafe_allow_html=True,
                )
                st.write(safe_text(item["comment_text"]))
                st.code(safe_text(item["reply_text"]))
                target_url = item.get("target_url") or item.get("comment_url") or item.get("post_url")
                if target_url:
                    st.markdown(f"[Open Target]({target_url})")
                if item.get("posting_error"):
                    st.error(item["posting_error"])
                if item.get("posted_at"):
                    st.caption(f"Posted at {item['posted_at']}")
                if status_value == "FAILED":
                    if st.button(
                        "Retry (re-approve)",
                        key=f"retry_{item['reply_id']}",
                        use_container_width=False,
                    ):
                        approve_reply(item["reply_id"])
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
