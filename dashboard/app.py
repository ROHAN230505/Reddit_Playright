from collections import Counter

import requests
import streamlit as st

API = "http://backend:8000"


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


def load_subreddit_content(subreddit: str, post_limit: int, comment_limit: int):
    return api_get(
        f"/subreddits/{subreddit}/content",
        params={"post_limit": post_limit, "comment_limit": comment_limit},
    )


def load_replies(status: str, limit: int, subreddit: str | None = None):
    params = {"status": status, "limit": limit}
    if subreddit and subreddit != "All":
        params["subreddit"] = subreddit
    return api_get("/replies", params=params)


def safe_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\u00a0", " ").strip()
    try:
        repaired = text.encode("latin1").decode("utf-8")
        if repaired.count("�") <= text.count("�"):
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


st.set_page_config(page_title="Reddit Reply Dashboard", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(249, 115, 22, 0.16), transparent 24%),
            radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), transparent 18%),
            linear-gradient(180deg, #0b1220 0%, #111827 52%, #0f172a 100%);
    }
    .block-container {
        max-width: 1500px;
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    .hero {
        padding: 1.1rem 1.25rem;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 22px;
        background:
            radial-gradient(circle at right top, rgba(249,115,22,0.18), transparent 28%),
            linear-gradient(135deg, rgba(15,23,42,0.94), rgba(30,41,59,0.88));
        box-shadow: 0 16px 40px rgba(0,0,0,0.22);
        margin-bottom: 1.1rem;
    }
    .hero-grid {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        align-items: flex-start;
    }
    .hero-copy {
        flex: 1 1 auto;
        min-width: 0;
    }
    .hero h1 {
        margin: 0;
        font-size: 2.2rem;
        line-height: 1.04;
    }
    .hero p {
        margin: 0.55rem 0 0;
        color: #cbd5e1;
        max-width: 760px;
        font-size: 0.98rem;
    }
    .hero-stack {
        display: flex;
        flex-direction: column;
        gap: 0.45rem;
        min-width: 230px;
    }
    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 0.7rem;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(15, 23, 42, 0.62);
        color: #dbeafe;
        font-size: 0.84rem;
        white-space: nowrap;
    }
    .panel {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        background: rgba(15, 23, 42, 0.72);
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
    }
    .metric-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.82);
        padding: 0.9rem 1rem;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .metric-value {
        font-size: 1.7rem;
        font-weight: 700;
        margin-top: 0.2rem;
    }
    .feed-card, .draft-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.88);
        padding: 1rem;
        margin-bottom: 0.95rem;
    }
    .feed-meta, .draft-meta {
        color: #94a3b8;
        font-size: 0.84rem;
        margin-bottom: 0.5rem;
    }
    .subreddit-chip {
        display: inline-block;
        padding: 0.32rem 0.62rem;
        border-radius: 999px;
        background: rgba(249,115,22,0.14);
        color: #fdba74;
        font-weight: 600;
        margin-bottom: 0.6rem;
    }
    .section-note {
        color: #94a3b8;
        font-size: 0.92rem;
        margin-top: -0.2rem;
        margin-bottom: 0.8rem;
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

selected_subreddit = st.session_state.selected_subreddit
pending_replies = load_replies("PENDING", 120, selected_subreddit)
done_replies = load_replies("DONE", 80, selected_subreddit)
ranked_pending = sorted(pending_replies, key=reply_value, reverse=True)
selected_content = load_subreddit_content(selected_subreddit, 12, 5) if selected_subreddit else None

draft_counts = Counter(item["subreddit"] for item in pending_replies)
top_sources = " | ".join(
    f"r/{name}: {count}"
    for name, count in draft_counts.most_common(6)
) if draft_counts else "No pending drafts yet"

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-grid">
        <div class="hero-copy">
          <h1>Reddit Reply Command Center</h1>
          <p>Inspect tracked subreddit conversations, trigger scrapes when needed, and work pending versus done replies without losing context.</p>
        </div>
        <div class="hero-stack">
          <div class="hero-pill">Selected: r/{selected_subreddit or "none"}</div>
          <div class="hero-pill">Auto scrape: every 6 hours</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

sidebar_col, main_col = st.columns([1.0, 2.4], gap="large")

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
        f'<div class="metric-card"><div class="metric-label">Done Replies</div><div class="metric-value">{len(done_replies)}</div></div>',
        unsafe_allow_html=True,
    )
    metric4.markdown(
        f'<div class="metric-card"><div class="metric-label">Selected Posts</div><div class="metric-value">{selected_content["post_count"] if selected_content else 0}</div></div>',
        unsafe_allow_html=True,
    )

    feed_tab, pending_tab, done_tab = st.tabs(["Subreddit Feed", "Pending Replies", "Done Replies"])

    with feed_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Selected Subreddit Feed")
        st.markdown(
            f'<div class="section-note">Showing stored posts and top comments for <strong>r/{selected_subreddit}</strong>.</div>'
            if selected_subreddit else '<div class="section-note">Select a subreddit to inspect its posts and comments.</div>',
            unsafe_allow_html=True,
        )
        if selected_subreddit:
            st.markdown(f'<div class="subreddit-chip">r/{selected_subreddit}</div>', unsafe_allow_html=True)

        if selected_content and selected_content["posts"]:
            for post in selected_content["posts"]:
                st.markdown('<div class="feed-card">', unsafe_allow_html=True)
                st.markdown(f"### {safe_text(post['title'])}")
                st.markdown(
                    f'<div class="feed-meta">{post["upvotes"]} post upvotes | {post["number_of_comments"]} comments</div>',
                    unsafe_allow_html=True,
                )
                body = safe_text(post.get("body"))
                if body:
                    st.write(body[:900])
                st.markdown(f"[Open Thread]({post['url']})")
                if post["top_comments"]:
                    st.caption("Top comments")
                    for comment in post["top_comments"]:
                        st.markdown(
                            f'<div class="feed-meta">{comment["upvotes"]} comment upvotes | {safe_text(comment["author"] or "unknown author")}</div>',
                            unsafe_allow_html=True,
                        )
                        st.write(safe_text(comment["text"]))
                        if comment["comment_url"]:
                            st.markdown(f"[Open Comment]({comment['comment_url']})")
                        st.markdown("---")
                else:
                    st.caption("No comments stored yet for this post.")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No scraped content is stored yet for this subreddit. Click the subreddit name, then scrape it to load posts and comments.")
        st.markdown("</div>", unsafe_allow_html=True)

    with pending_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Pending Replies")
        st.markdown(
            f'<div class="section-note">Replies are ranked by post traction, comment traction, and discussion size. Top sources right now: {top_sources}</div>',
            unsafe_allow_html=True,
        )
        if ranked_pending:
            for item in ranked_pending:
                st.markdown('<div class="draft-card">', unsafe_allow_html=True)
                st.markdown(f"### {safe_text(item['post_title'])}")
                st.markdown(
                    f'<div class="draft-meta">Value score: {reply_value(item)} | r/{item["subreddit"]} | post {item["post_upvotes"]} upvotes | comment {item["comment_upvotes"]} upvotes | {item["post_comment_count"]} comments</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("Post context", expanded=False):
                    post_body = safe_text(item.get("post_body"))
                    if post_body:
                        st.write(post_body)
                    st.markdown(f"[Open Thread]({item['post_url']})")
                st.write("Comment")
                st.write(safe_text(item["comment_text"]))
                if item["comment_url"]:
                    st.markdown(f"[Open Comment]({item['comment_url']})")
                st.write("Draft reply")
                st.code(safe_text(item["reply_text"]))

                action_cols = st.columns([1, 6])
                if action_cols[0].button("Done", key=f"done_{item['reply_id']}", use_container_width=True):
                    api_patch(f"/replies/{item['reply_id']}", json={"status": "DONE"})
                    st.rerun()
                badges = []
                if item["is_ai_relevant"]:
                    badges.append("AI relevant")
                if item["includes_promo"]:
                    badges.append("sentx.ai")
                if badges:
                    action_cols[1].caption(" | ".join(badges))
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No pending drafted replies are available for the current view.")
        st.markdown("</div>", unsafe_allow_html=True)

    with done_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Done Replies")
        st.markdown(
            '<div class="section-note">These are replies you already marked done for the current subreddit scope.</div>',
            unsafe_allow_html=True,
        )
        if done_replies:
            for item in done_replies:
                st.markdown('<div class="draft-card">', unsafe_allow_html=True)
                st.markdown(f"### {safe_text(item['post_title'])}")
                st.markdown(
                    f'<div class="draft-meta">r/{item["subreddit"]} | post {item["post_upvotes"]} upvotes | comment {item["comment_upvotes"]} upvotes</div>',
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
