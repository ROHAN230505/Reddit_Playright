"use client";

import { memo, useState } from "react";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { Check, ExternalLink, SkipForward, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { AccountActivity, RedditAccountItem, ReplyItem } from "@/lib/api";
import {
  deriveSlotState,
  formatCountdown,
  type SlotState,
} from "@/lib/queue-slots";
import { cn } from "@/lib/utils";

const HOLD_REASON_LABELS: Record<string, string> = {
  blocked_risky_keyword: "Held: sensitive topic",
  blocked_promo_fit: "Held: promo didn't fit",
  blocked_normal_daily_cap: "Held: daily cap",
  blocked_promo_daily_cap: "Held: promo cap",
  blocked_subreddit_cap: "Held: per-sub cap",
};

function holdReasonLabel(reply: ReplyItem): string {
  if (reply.auto_approval_reason && HOLD_REASON_LABELS[reply.auto_approval_reason]) {
    return HOLD_REASON_LABELS[reply.auto_approval_reason];
  }
  if (reply.auto_approval_reason) return `Held: ${reply.auto_approval_reason}`;
  return "Needs review";
}

// Keep this in sync with the regex in backend/app/schemas.py — both reject the
// same URLs so the button stays in lockstep with what the API will accept.
const REDDIT_COMMENT_URL_RE =
  /^https?:\/\/(?:[\w-]+\.)?reddit\.com\/(?:.*?\/comments\/[A-Za-z0-9_-]+|(?:r\/[\w-]+\/)?s\/[A-Za-z0-9_-]+)/i;

function isValidRedditCommentUrl(value: string): boolean {
  return REDDIT_COMMENT_URL_RE.test(value.trim());
}

function AssignedSubsBadge({ subs }: { subs: string[] }) {
  if (!subs.length) {
    return (
      <Badge
        variant="outline"
        className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
        title="No subreddits assigned — this slot pulls from the full pending pool. Click 'Auto-assign subreddits' to balance the workload."
      >
        any sub
      </Badge>
    );
  }
  const preview = subs.slice(0, 2).join(", ");
  const more = subs.length > 2 ? ` +${subs.length - 2}` : "";
  return (
    <Badge
      variant="secondary"
      className="max-w-[260px] truncate text-[10px] font-medium"
      title={subs.join(", ")}
    >
      {preview}
      {more}
    </Badge>
  );
}

function slotNeedsTick(state: SlotState) {
  return state.kind === "cooldown" || state.kind === "hourly" || state.kind === "daily";
}

export type QueueSlotCardProps = {
  slot: number;
  slotPosition: number;
  slotTotal: number;
  account: RedditAccountItem | null;
  reply: ReplyItem | null;
  activity: AccountActivity | undefined;
  active?: boolean;
  busy: boolean;
  editText: string;
  postedUrl: string;
  brandName: string | null;
  onEditChange: (replyId: number, value: string) => void;
  onPostedUrlChange: (replyId: number, value: string) => void;
  onApprove: (reply: ReplyItem, text: string) => void;
  onMarkDone: (
    reply: ReplyItem,
    accountId: number,
    username: string,
    postedUrl: string,
    text: string,
  ) => void;
  onSave: (reply: ReplyItem, text: string) => void;
  onDismiss: (reply: ReplyItem) => void;
  onSkip: (reply: ReplyItem) => void;
};

export const QueueSlotCard = memo(function QueueSlotCard({
  slot,
  slotPosition,
  slotTotal,
  account,
  reply,
  activity,
  active = true,
  busy,
  editText,
  postedUrl,
  brandName,
  onEditChange,
  onPostedUrlChange,
  onApprove,
  onMarkDone,
  onSave,
  onDismiss,
  onSkip,
}: QueueSlotCardProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const state: SlotState = account
    ? deriveSlotState(account, activity, nowMs)
    : { kind: "disabled" };
  const needsTick = Boolean(active && account && slotNeedsTick(state));
  useVisibleInterval(() => setNowMs(Date.now()), needsTick ? 1000 : null);

  const editingText = reply ? editText : "";
  const postedUrlInput = reply ? postedUrl : "";
  const trimmedPostedUrl = postedUrlInput.trim();
  const hasPostedUrlInput = trimmedPostedUrl.length > 0;
  const isPostedUrlValid = hasPostedUrlInput && isValidRedditCommentUrl(trimmedPostedUrl);
  const isLocked = state.kind !== "active";
  const changed = reply ? editingText !== reply.reply_text : false;
  const slotLabel = `Slot ${slot}`;
  const duplicateLabel =
    account && slotTotal > 1 ? `duplicate ${slotPosition + 1}/${slotTotal}` : null;

  if (!account) {
    return (
      <Card className="overflow-hidden border-dashed p-5 shadow-none">
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="outline" className="font-mono text-[11px]">
            {slotLabel}
          </Badge>
          {duplicateLabel && (
            <Badge variant="secondary" className="text-[11px] font-semibold text-amber-700 dark:text-amber-400">
              {duplicateLabel}
            </Badge>
          )}
          <span className="text-muted-foreground">No account assigned</span>
        </div>
        <div className="mt-6 text-center text-xs text-muted-foreground">
          Assign an account with profile slot {slot} in Settings / Accounts.
        </div>
      </Card>
    );
  }

  const dimClass = isLocked ? "opacity-60" : "";
  const overlayInfo = (() => {
    if (state.kind === "cooldown")
      return { label: "Cooldown", seconds: state.secondsLeft, tone: "amber" as const };
    if (state.kind === "hourly")
      return {
        label: `Hourly cap ${state.used}/${state.cap}`,
        seconds: state.resetsInSeconds,
        tone: "rose" as const,
      };
    if (state.kind === "daily")
      return {
        label: `Daily cap ${state.used}/${state.cap}`,
        seconds: state.resetsInSeconds,
        tone: "rose" as const,
      };
    return null;
  })();

  return (
    <Card
      className={cn(
        "group relative overflow-hidden shadow-none transition-all",
        isLocked ? "border-border" : "hover:border-primary/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b bg-muted/40 px-3 py-2 text-xs">
        <Badge
          variant="outline"
          className="font-mono text-[11px]"
          title={account.profile_summary ?? ""}
        >
          {slotLabel}
        </Badge>
        <span className="font-mono font-semibold text-foreground">u/{account.username}</span>
        {duplicateLabel && (
          <Badge variant="secondary" className="text-[11px] font-semibold text-amber-700 dark:text-amber-400">
            {duplicateLabel}
          </Badge>
        )}
        <AssignedSubsBadge subs={account.assigned_subreddits ?? []} />
        {(account.status === "BANNED" || account.reddit_health === "BANNED") && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            banned
          </Badge>
        )}
        {account.reddit_health === "SESSION_DEAD" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            session dead
          </Badge>
        )}
        {account.reddit_health === "NO_COOKIES" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            no cookies
          </Badge>
        )}
        {!account.is_enabled && account.reddit_health !== "BANNED" && account.status !== "BANNED" && (
          <Badge variant="outline" className="text-[10px] uppercase tracking-wide text-muted-foreground">
            disabled
          </Badge>
        )}
        {state.kind === "cooldown" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            cooldown
          </Badge>
        )}
        {state.kind === "hourly" && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            hourly cap
          </Badge>
        )}
        {state.kind === "daily" && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            daily cap
          </Badge>
        )}
        {reply && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="font-medium text-foreground">
              {reply.platform === "glp"
                ? `glp/${reply.platform_section ?? "forum"}`
                : reply.platform === "chan"
                ? `/${reply.platform_section ?? reply.subreddit ?? "board"}/`
                : `r/${reply.subreddit}`}
            </span>
            <Badge
              variant="outline"
              className={cn(
                "text-[10px] font-medium",
                reply.includes_promo
                  ? "border-amber-500/30 text-amber-700 dark:text-amber-400"
                  : "border-primary/30 text-primary",
              )}
            >
              {reply.includes_promo ? "promo" : "normal"}
            </Badge>
            {brandName && (
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px] font-medium",
                  brandName === "untagged"
                    ? "border-destructive/30 text-destructive"
                    : "border-primary/30 text-foreground",
                )}
              >
                {brandName}
              </Badge>
            )}
            <Badge variant="secondary" className="text-[10px] font-medium">
              {holdReasonLabel(reply)}
            </Badge>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground">
              #{reply.reply_id}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Skip reply #${reply.reply_id} and pull next from queue`}
              title="Skip — pull the next reply from the queue"
              disabled={busy}
              onClick={() => onSkip(reply)}
              className="ml-1 h-5 w-5 text-muted-foreground hover:text-destructive"
            >
              <SkipForward />
            </Button>
          </>
        )}
        {!reply && state.kind === "active" && (
          <span className="ml-auto text-muted-foreground">queue empty</span>
        )}
      </div>

      {state.kind === "cooldown" && (
        <div className="flex items-center justify-between border-b border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          <span>Ready in</span>
          <span className="font-mono font-semibold">
            {formatCountdown(state.secondsLeft)}
          </span>
        </div>
      )}
      {state.kind === "hourly" && (
        <div className="flex items-center justify-between border-b border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          <span>
            Hourly cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "daily" && (
        <div className="flex items-center justify-between border-b border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          <span>
            Daily cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "banned" && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Banned on Reddit
          {state.sessionAlive
            ? " — session still logged in, but the public profile is banned. Cannot post."
            : " — public profile is the source of truth."}
          {state.detail ? ` ${state.detail}` : ""}
        </div>
      )}
      {state.kind === "session_dead" && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          Session dead — cookies are not authenticated. {state.detail ?? "Paste fresh cookies."}
        </div>
      )}
      {state.kind === "no_cookies" && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          No session cookies stored. Paste cookies before this slot can post.
        </div>
      )}
      {state.kind === "proxy_dead" && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Proxy dead — cannot reach Reddit. {state.detail ?? ""}
        </div>
      )}
      {state.kind === "disabled" && (
        <div className="border-b bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
          Account disabled — re-enable in Settings / Accounts to use this slot.
        </div>
      )}

      {reply ? (
        <div className={cn("grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]", dimClass)}>
          <div className="min-w-0 space-y-2">
            <h3
              className="line-clamp-2 text-sm font-semibold text-foreground"
              title={reply.post_title}
            >
              {reply.post_title}
            </h3>
            <blockquote className="line-clamp-4 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
              {reply.comment_text}
            </blockquote>
            <div className="flex flex-wrap items-center gap-3 text-[11px]">
              {reply.comment_url && (
                <a
                  href={reply.comment_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-foreground hover:underline"
                >
                  Open on reddit
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              {reply.comment_author && (
                <span className="font-mono text-muted-foreground">u/{reply.comment_author}</span>
              )}
              <span className="text-muted-foreground">↑{reply.comment_upvotes} cmt</span>
              <span className="text-muted-foreground">↑{reply.post_upvotes} post</span>
            </div>
          </div>

          <div className="min-w-0 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Draft reply
              </span>
              {changed && (
                <span className="text-[10px] font-medium text-amber-700 dark:text-amber-400">Unsaved</span>
              )}
            </div>
            <Textarea
              value={editingText}
              readOnly={isLocked}
              onChange={(event) => onEditChange(reply.reply_id, event.target.value)}
              className="min-h-[100px] text-sm"
            />
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label
                  htmlFor={`posted-url-${reply.reply_id}`}
                  className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Posted reply URL
                </Label>
                {hasPostedUrlInput && !isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-destructive">
                    Not a Reddit comment link
                  </span>
                )}
                {isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                    Looks good
                  </span>
                )}
              </div>
              <Input
                id={`posted-url-${reply.reply_id}`}
                type="url"
                inputMode="url"
                placeholder="https://www.reddit.com/r/.../comments/..."
                value={postedUrlInput}
                readOnly={isLocked}
                onChange={(event) => onPostedUrlChange(reply.reply_id, event.target.value)}
                className={cn(
                  "h-9 text-xs",
                  hasPostedUrlInput && !isPostedUrlValid && "border-destructive focus-visible:ring-destructive",
                )}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() =>
                  onMarkDone(reply, account.id, account.username, trimmedPostedUrl, editingText)
                }
                disabled={
                  busy ||
                  isLocked ||
                  !editingText.trim() ||
                  !isPostedUrlValid
                }
                title={
                  isLocked
                    ? "Slot is in cooldown or at limit"
                    : !isPostedUrlValid
                    ? "Paste the Reddit comment URL above to enable"
                    : "Record this as posted by this account and start cooldown"
                }
              >
                Mark done
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onApprove(reply, editingText)}
                disabled={busy || isLocked || !editingText.trim()}
                title="Approve for the worker to post"
              >
                <Check />
                Approve
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onSave(reply, editingText)}
                disabled={busy || !editingText.trim() || !changed}
                title="Save edits without changing status"
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="ml-auto text-destructive hover:text-destructive"
                onClick={() => onDismiss(reply)}
                disabled={busy || isLocked}
              >
                <X />
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-6 text-center text-xs text-muted-foreground">
          {state.kind === "active"
            ? "No pending reply for this slot — generate more or scrape new content."
            : "Slot will pick the next pending reply when it becomes available."}
        </div>
      )}

      {overlayInfo && (
        <div
          className={cn(
            "pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 bg-background/80 backdrop-blur-[2px]",
            overlayInfo.tone === "amber"
              ? "text-amber-700 dark:text-amber-400"
              : "text-destructive",
          )}
          aria-live="polite"
        >
          <div className="text-[11px] font-semibold uppercase tracking-wider">
            {overlayInfo.label}
          </div>
          <div className="font-mono text-4xl font-bold tabular-nums text-foreground">
            {formatCountdown(overlayInfo.seconds)}
          </div>
          <div className="text-[10px] opacity-80">
            {state.kind === "cooldown" ? "next post unlocks at 0:00" : "resets in"}
          </div>
        </div>
      )}
    </Card>
  );
});
