"use client";

import { useEffect, useState } from "react";
import { api, type ContentPost, type SubredditContent, type TrackedSubreddit } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, Input, Select } from "@/components/legacy-ui";
import { useSelectedSubreddit } from "@/lib/hooks/use-selected-subreddit";
import { EmptyState, Pagination } from "@/components/sections/shared";

type RelevanceFilter = "all" | "promo" | "normal";

export default function FeedSection() {
  const [selectedSubreddit, setSelectedSubreddit] = useSelectedSubreddit();
  const [subreddits, setSubreddits] = useState<TrackedSubreddit[]>([]);
  const [content, setContent] = useState<SubredditContent | null>(null);
  const [page, setPage] = useState(1);
  const [relevance, setRelevance] = useState<RelevanceFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    api.trackedSubreddits().then((tracked) => {
      setSubreddits(tracked);
      if (!selectedSubreddit && tracked[0]) setSelectedSubreddit(tracked[0].name);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedSubreddit) {
      setContent(null);
      return;
    }
    api.content(selectedSubreddit, page, 5, 5, dateFrom, dateTo).then(setContent).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSubreddit, page, dateFrom, dateTo]);

  const totalPages = Math.max(1, Math.ceil((content?.total_posts || 0) / (content?.page_size || 5)));

  return (
    <Card className="p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Subreddit Feed</h2>
          <p className="text-sm text-muted">
            Posts, comments, pagination, and filters for the selected subreddit.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-4 xl:w-[760px]">
          <Select
            value={selectedSubreddit}
            onChange={(event) => {
              setSelectedSubreddit(event.target.value);
              setPage(1);
            }}
          >
            {subreddits.map((item) => (
              <option key={item.id} value={item.name}>
                r/{item.name}
              </option>
            ))}
          </Select>
          <Select
            value={relevance}
            onChange={(event) => setRelevance(event.target.value as RelevanceFilter)}
          >
            <option value="all">All relevance</option>
            <option value="promo">Promo</option>
            <option value="normal">Normal</option>
          </Select>
          <Input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
          <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {(content?.posts || []).map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
        {!subreddits.length && (
          <EmptyState
            title="No subreddits tracked"
            description="Add a subreddit before viewing the feed."
          />
        )}
        {!!subreddits.length && !content?.posts?.length && (
          <EmptyState
            title="No posts found"
            description="Change the date filters or run a fresh scrape for this subreddit."
          />
        )}
      </div>
      <Pagination
        page={page}
        totalPages={totalPages}
        total={content?.total_posts || 0}
        onPage={setPage}
      />
    </Card>
  );
}

function PostCard({ post }: { post: ContentPost }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold">{post.title}</h3>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
            <span>{post.upvotes} upvotes</span>
            <span>{post.number_of_comments} comments</span>
            <span>{formatDate(post.created_at)}</span>
          </div>
        </div>
        <a
          className="inline-flex items-center gap-1 text-sm font-medium text-accent"
          href={post.url}
          target="_blank"
          rel="noreferrer"
        >
          Open
        </a>
      </div>
      {post.body && (
        <p className="mt-3 line-clamp-4 text-sm leading-6 text-foreground">{post.body}</p>
      )}
      <div className="mt-4 space-y-2">
        {post.top_comments.map((comment) => (
          <div
            key={comment.id}
            className="rounded-md border-l-4 border-teal-600 bg-muted p-3 text-sm"
          >
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>{comment.upvotes} upvotes</span>
              <span>{comment.author || "unknown"}</span>
              <span>{formatDate(comment.created_at)}</span>
              {comment.comment_url && (
                <a
                  className="text-accent"
                  href={comment.comment_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open comment
                </a>
              )}
            </div>
            {comment.text}
          </div>
        ))}
      </div>
    </div>
  );
}
