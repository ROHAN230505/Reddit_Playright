"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { QueueSlotCard } from "@/components/reddit/queue-slot-card";
import {
  api,
  type BrandConfig,
  type RedditAutomationSummary,
  type ReplyItem,
} from "@/lib/api";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";
import { usePendingReplies, useUpdateReply } from "@/lib/hooks/use-replies";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";
import { assignQueueSlots } from "@/lib/queue-slots";
import { cn } from "@/lib/utils";

function LoadingGrid() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-64 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Load error</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{message}</p>
        <p className="text-destructive/80">
          Most likely the dashboard can&apos;t reach the API at{" "}
          <code>{process.env.NEXT_PUBLIC_API_BASE_URL || "(unset)"}</code> from
          your browser. Open DevTools → Network and check the failing request.
        </p>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function QueueBoard({ active = true }: { active?: boolean }) {
  const queryClient = useQueryClient();
  const updateReply = useUpdateReply();
  const [brandFilter, setBrandFilter] = useState("all");
  const brandId =
    brandFilter !== "all" && Number.isFinite(Number(brandFilter))
      ? Number(brandFilter)
      : undefined;

  const healthQuery = useAccountsHealth(false, active);
  const pendingQuery = usePendingReplies(brandId, active);
  const brandsQuery = useQuery({
    queryKey: queryKeys.brands(),
    queryFn: () => api.brands().catch(() => [] as BrandConfig[]),
    enabled: active,
    placeholderData: (previous) => previous,
  });
  const automationQuery = useQuery({
    queryKey: queryKeys.redditAutomation({ limit: 5 }),
    queryFn: () => api.redditAutomation({ limit: 5 }),
    enabled: active,
    refetchInterval: active ? visibleRefetchInterval(15_000) : false,
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });
  const queueQuery = useQuery({
    queryKey: queryKeys.workerQueue("reddit"),
    queryFn: async () => {
      try {
        return await api.workerQueue("reddit");
      } catch {
        return { counts: {} as Record<string, number> };
      }
    },
    enabled: active,
    refetchInterval: active ? visibleRefetchInterval(15_000) : false,
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });

  const accounts = healthQuery.data?.accounts ?? [];
  const activity = healthQuery.data?.activity ?? {};
  const pending = pendingQuery.data ?? [];
  const brands = brandsQuery.data ?? [];
  const automationSummary = automationQuery.data ?? null;
  const queueCounts = queueQuery.data?.counts ?? {};

  const [edits, setEdits] = useState<Record<number, string>>({});
  const [postedUrls, setPostedUrls] = useState<Record<number, string>>({});
  const [actionBusy, setActionBusy] = useState(false);
  const busy = actionBusy || updateReply.isPending;
  const hasLoadedOnce = healthQuery.isFetched && pendingQuery.isFetched;
  const loadError =
    (healthQuery.error instanceof Error && healthQuery.error.message) ||
    (pendingQuery.error instanceof Error && pendingQuery.error.message) ||
    null;

  const invalidateBoard = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["replies"] });
    void queryClient.invalidateQueries({ queryKey: ["accounts-health"] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.workerQueue("reddit") });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.redditAutomation({ limit: 5 }),
    });
  }, [queryClient]);

  const runApi = useCallback(
    async (action: () => Promise<unknown>, successMsg: string) => {
      setActionBusy(true);
      try {
        await action();
        toast.success(successMsg);
        invalidateBoard();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Action failed");
      } finally {
        setActionBusy(false);
      }
    },
    [invalidateBoard],
  );

  const assignedSlots = useMemo(
    () => assignQueueSlots({ accounts, pending, activity, brands }),
    [accounts, pending, activity, brands],
  );

  const brandNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const brand of brands) {
      if (brand.id != null) map.set(brand.id, brand.name);
    }
    return map;
  }, [brands]);

  const untaggedCount = useMemo(
    () => pending.filter((item) => !item.brand_id).length,
    [pending],
  );
  const enabledCount = useMemo(
    () => accounts.filter((account) => account.is_enabled).length,
    [accounts],
  );
  const hasVisibleReply = assignedSlots.some((slot) => slot.reply);

  const onEditChange = useCallback((replyId: number, value: string) => {
    setEdits((prev) => ({ ...prev, [replyId]: value }));
  }, []);
  const onPostedUrlChange = useCallback((replyId: number, value: string) => {
    setPostedUrls((prev) => ({ ...prev, [replyId]: value }));
  }, []);
  const onApprove = useCallback(
    (reply: ReplyItem, text: string) => {
      updateReply.mutate({
        id: reply.reply_id,
        status: "APPROVED",
        reply_text: text,
      });
    },
    [updateReply],
  );
  const onSave = useCallback(
    (reply: ReplyItem, text: string) => {
      updateReply.mutate({
        id: reply.reply_id,
        reply_text: text,
      });
    },
    [updateReply],
  );
  const onDismiss = useCallback(
    (reply: ReplyItem) => {
      if (!window.confirm(`Dismiss reply #${reply.reply_id}?`)) return;
      updateReply.mutate({
        id: reply.reply_id,
        status: "DISMISSED",
      });
    },
    [updateReply],
  );
  const onSkip = useCallback(
    (reply: ReplyItem) => {
      updateReply.mutate({
        id: reply.reply_id,
        status: "DISMISSED",
      });
    },
    [updateReply],
  );
  const onMarkDone = useCallback(
    (
      reply: ReplyItem,
      accountId: number,
      username: string,
      postedUrl: string,
      text: string,
    ) => {
      void runApi(
        async () => {
          await api.markReplyPostedByAccount(
            reply.reply_id,
            accountId,
            postedUrl,
            text,
          );
          setPostedUrls((prev) => {
            const { [reply.reply_id]: _drop, ...rest } = prev;
            return rest;
          });
        },
        `Marked posted by ${username}`,
      );
    },
    [runApi],
  );

  if (healthQuery.isPending && !healthQuery.data) {
    return <LoadingGrid />;
  }

  if (healthQuery.isError && !healthQuery.data) {
    return (
      <ErrorBanner
        message={loadError || "Failed to load"}
        onRetry={() => {
          void healthQuery.refetch();
          void pendingQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {loadError ? (
        <ErrorBanner
          message={loadError}
          onRetry={() => {
            void healthQuery.refetch();
            void pendingQuery.refetch();
          }}
        />
      ) : null}

      {automationSummary && <QueueAutomationStatus summary={automationSummary} />}

      <Card className="p-3 shadow-none">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-foreground">Reddit review board</span>
          <span className="text-muted-foreground">
            Edit and dismiss here. Approve queues the draft for the poster.
            Mark done after you post it yourself.
          </span>
          <Badge variant="secondary">
            {queueCounts.PENDING ?? pending.length} pending
          </Badge>
          <Badge variant="outline" className="border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
            {queueCounts.APPROVED ?? 0} approved
          </Badge>
          <Badge variant="outline">
            {untaggedCount} untagged
          </Badge>
          <Select
            value={brandFilter}
            onValueChange={setBrandFilter}
          >
            <SelectTrigger
              className="h-8 w-44"
              title="Filter the pending queue by brand"
            >
              <SelectValue placeholder="All brands" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All brands</SelectItem>
              {brands.map((brand) => (
                <SelectItem
                  key={brand.id ?? brand.name}
                  value={String(brand.id ?? brand.name)}
                >
                  {brand.name}
                  {brand.is_active ? " (default)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            title="Scrape every tracked subreddit now"
            onClick={() =>
              void runApi(async () => {
                await api.scrapeAll(15);
              }, "Scrape queued for tracked subs")
            }
          >
            Scrape now
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || untaggedCount === 0}
            title="Stamp missing brand_id from the subreddit owner"
            onClick={() =>
              void runApi(
                () => api.stampReplyBrands(),
                "Tagged untagged drafts with their brand",
              )
            }
          >
            Stamp brands
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || enabledCount === 0}
            title="Distribute tracked subreddits across enabled accounts, balanced by posts in the last 7 days."
            onClick={() =>
              void runApi(async () => {
                await api.autoAssignSubreddits();
              }, "Subreddits assigned across accounts")
            }
          >
            Auto-assign subreddits
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={busy || enabledCount === 0}
            title="Run the LLM on already-scraped comments (no Apify) that don't have a reply yet, focusing on assigned subreddits with empty queues."
            onClick={() => {
              const enabled = accounts.filter((a) => a.is_enabled);
              const pendingByLowerSub = new Map<string, number>();
              for (const r of pending) {
                const k = (r.subreddit ?? "").toLowerCase();
                pendingByLowerSub.set(k, (pendingByLowerSub.get(k) ?? 0) + 1);
              }
              const targetSubs = new Set<string>();
              for (const a of enabled) {
                for (const sub of a.assigned_subreddits ?? []) {
                  if ((pendingByLowerSub.get(sub.toLowerCase()) ?? 0) < 5) {
                    targetSubs.add(sub);
                  }
                }
              }
              const list = [...targetSubs];
              if (!list.length) {
                toast.success("Every assigned subreddit already has 5+ pending replies");
                return;
              }
              void runApi(async () => {
                await api.generateRepliesFromExisting(list, 20);
              }, `Queued ${list.length} generation jobs`);
            }}
          >
            Generate for empty slots
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || !hasVisibleReply}
            title="Approve every draft currently shown on a slot so the poster can claim it"
            onClick={() => {
              const ids = assignedSlots
                .map((slot) => slot.reply?.reply_id)
                .filter((id): id is number => typeof id === "number");
              if (!ids.length) return;
              if (!window.confirm(`Approve ${ids.length} visible drafts for posting?`)) return;
              void runApi(
                () => api.bulkUpdateReplies(ids, "APPROVED"),
                `Approved ${ids.length} drafts`,
              );
            }}
          >
            Approve visible
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={busy || !hasVisibleReply}
            title="Dismiss every draft currently shown on a slot"
            onClick={() => {
              const ids = assignedSlots
                .map((slot) => slot.reply?.reply_id)
                .filter((id): id is number => typeof id === "number");
              if (!ids.length) return;
              if (!window.confirm(`Dismiss ${ids.length} visible drafts?`)) return;
              void runApi(
                () => api.bulkUpdateReplies(ids, "DISMISSED"),
                `Dismissed ${ids.length} drafts`,
              );
            }}
          >
            Dismiss visible
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {assignedSlots.filter((slot) => slot.account).length} account cards · {pending.length} pending in queue
            {!hasLoadedOnce && !loadError && " · loading…"}
          </span>
        </div>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-3">
        {assignedSlots.map(({ slot, slotPosition, slotTotal, account, reply }) => (
          <QueueSlotCard
            key={account ? `${slot}-${account.id}` : `empty-${slot}`}
            slot={slot}
            slotPosition={slotPosition}
            slotTotal={slotTotal}
            account={account}
            reply={reply}
            activity={account ? activity[account.id] : undefined}
            active={active}
            busy={busy}
            editText={
              reply
                ? edits[reply.reply_id] !== undefined
                  ? edits[reply.reply_id]
                  : reply.reply_text
                : ""
            }
            postedUrl={reply ? postedUrls[reply.reply_id] ?? "" : ""}
            brandName={
              reply?.brand_id
                ? brandNameById.get(reply.brand_id) ?? "tagged"
                : reply
                  ? "untagged"
                  : null
            }
            onEditChange={onEditChange}
            onPostedUrlChange={onPostedUrlChange}
            onApprove={onApprove}
            onMarkDone={onMarkDone}
            onSave={onSave}
            onDismiss={onDismiss}
            onSkip={onSkip}
          />
        ))}
      </div>

      {!accounts.length && (
        <Card className="p-8 text-center shadow-none">
          <p className="text-sm font-medium">No accounts yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add Reddit accounts in Settings / Accounts - each profile slot appears here once an account is assigned to it.
          </p>
          <Button asChild className="mt-4">
            <Link href="/settings?tab=accounts">Go to accounts</Link>
          </Button>
        </Card>
      )}
    </div>
  );
}

function QueueAutomationStatus({ summary }: { summary: RedditAutomationSummary }) {
  const state = summary.current_state;
  const toneClass =
    state.state === "ready" || state.state === "posting"
      ? "border-emerald-500/30 bg-emerald-500/10"
      : state.state === "cooldown" || state.state === "idle_empty_queue"
        ? "border-amber-500/30 bg-amber-500/10"
        : "border-destructive/30 bg-destructive/10";
  const readyAccounts = summary.accounts.filter((account) => account.readiness_status === "ready").length;

  return (
    <Card className={cn("p-4 shadow-none", toneClass)}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="bg-background/80 font-semibold">
              {state.worker_running ? "Worker active" : "Worker not confirmed"}
            </Badge>
            <Badge variant="outline" className="bg-background/80 font-semibold">
              {state.title}
            </Badge>
          </div>
          <div className="mt-2 font-semibold text-foreground">{state.detail}</div>
          {state.blockers.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {state.blockers.slice(0, 3).map((blocker) => (
                <li key={blocker} className="break-words">{blocker}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="grid shrink-0 gap-2 text-sm sm:grid-cols-3 lg:min-w-[520px]">
          <QueueStatusFact label="Approved" value={String(state.approved_queue_count)} />
          <QueueStatusFact label="Ready accounts" value={`${readyAccounts} / ${summary.account_count}`} />
          <QueueStatusFact label="Active account" value={state.active_account_username ? `u/${state.active_account_username}` : "None"} />
        </div>
      </div>
    </Card>
  );
}

function QueueStatusFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/80 bg-background/60 p-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium text-foreground">{value}</div>
    </div>
  );
}
