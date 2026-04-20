import requests
import streamlit as st

API = "http://backend:8000"

st.set_page_config(page_title="Reddit AI Dashboard", layout="wide")
st.title("Reddit AI Dashboard")

with st.sidebar:
    st.header("Fetch Jobs")
    subreddits_raw = st.text_area("Subreddits", value="startups\nEntrepreneur")
    limit = st.number_input("Limit", min_value=1, max_value=500, value=50)
    if st.button("Run Fetch"):
        subreddits = [item.strip() for item in subreddits_raw.splitlines() if item.strip()]
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
