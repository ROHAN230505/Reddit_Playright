import requests
import streamlit as st

API = "http://backend:8000"


def load_tracked_subreddits():
    response = requests.get(f"{API}/tracked-subreddits", timeout=30)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Reddit AI Dashboard", layout="wide")
st.title("Reddit AI Dashboard")

with st.sidebar:
    st.header("Tracked Subreddits")
    tracked_subreddits = load_tracked_subreddits()
    new_subreddit = st.text_input("Add subreddit", placeholder="OpenAI")
    if st.button("Add Subreddit"):
        if new_subreddit.strip():
            response = requests.post(
                f"{API}/tracked-subreddits",
                json={"name": new_subreddit.strip()},
                timeout=30,
            )
            response.raise_for_status()
            st.success("Subreddit added")
            st.rerun()

    for item in tracked_subreddits:
        cols = st.columns([4, 1])
        cols[0].write(f"r/{item['name']}")
        if cols[1].button("Remove", key=f"remove_{item['id']}"):
            response = requests.delete(
                f"{API}/tracked-subreddits/{item['id']}",
                timeout=30,
            )
            response.raise_for_status()
            st.success("Subreddit removed")
            st.rerun()

    st.divider()
    st.header("Run Fetch")
    limit = st.number_input("Limit", min_value=1, max_value=500, value=50)
    if st.button("Run All Tracked"):
        response = requests.post(
            f"{API}/tracked-subreddits/run",
            params={"limit": int(limit)},
            timeout=30,
        )
        response.raise_for_status()
        st.success("Tracked subreddit jobs queued")
        st.json(response.json())

    manual_subreddits = st.text_area(
        "Manual subreddits",
        value="",
        placeholder="OpenAI\nMachineLearning",
    )
    if st.button("Run Manual Fetch"):
        subreddits = [
            item.strip().removeprefix("r/")
            for item in manual_subreddits.splitlines()
            if item.strip()
        ]
        response = requests.post(
            f"{API}/fetch",
            json={"subreddits": subreddits, "limit": int(limit)},
            timeout=30,
        )
        response.raise_for_status()
        st.success("Fetch jobs queued")
        st.json(response.json())

status = st.selectbox("Status", ["PENDING", "DONE"])
response = requests.get(f"{API}/replies", params={"status": status}, timeout=30)
response.raise_for_status()
data = response.json()

for item in data:
    st.subheader(item["post_title"])
    st.caption(f"r/{item['subreddit']}")
    st.markdown(f"[View Post]({item['post_url']})")
    st.write("Comment:")
    st.write(item["comment_text"])

    if item["comment_url"]:
        st.markdown(f"[View Comment]({item['comment_url']})")
    else:
        st.markdown(f"[View Post]({item['post_url']})")

    st.write("Draft Reply:")
    st.code(item["reply_text"])

    if st.button("Mark as Done", key=f"done_{item['reply_id']}"):
        patch_response = requests.patch(
            f"{API}/replies/{item['reply_id']}",
            json={"status": "DONE"},
            timeout=30,
        )
        patch_response.raise_for_status()
        st.success("Marked as done")
        st.rerun()

    tags = []
    if item["is_ai_relevant"]:
        tags.append("AI relevant")
    if item["includes_promo"]:
        tags.append("sentx.ai")
    if tags:
        st.caption(" | ".join(tags))
    st.divider()
