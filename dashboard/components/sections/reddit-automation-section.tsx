"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type RedditAutomationSummary } from "@/lib/api";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { formatDate, percent } from "@/lib/utils";
import {
  Badge,
  Card,
  FieldLabel,
  Input,
  SectionHeader,
  Select,
  Skeleton,
  StateMessage,
  TableShell,
  tableCellClassName,
  tableHeadClassName,
  tableRowClassName,
} from "@/components/legacy-ui";

const STATUS_OPTIONS = ["ALL", "POSTED", "FAILED", "POSTING", "APPROVED"];

export default function RedditAutomationSection() {
  const [summary, setSummary] = useState<RedditAutomationSummary | null>(null);
  const [error, setError] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [accountId, setAccountId] = useState("");
  const [subreddit, setSubreddit] = useState("");
  const [status, setStatus] = useState("ALL");

  const filters = useMemo(
    () => ({
      dateFrom,
      dateTo,
      accountId: accountId ? Number(accountId) : null,
      subreddit,
      status,
      limit: 30,
    }),
    [accountId, dateFrom, dateTo, status, subreddit],
  );

  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .redditAutomation(filters)
        .then((data) => {
          if (!alive) return;
          setSummary(data);
          setError("");
        })
        .catch((err) => {
          if (!alive) return;
          setError(err instanceof Error ? err.message : "Failed to load Reddit automation analytics.");
        });
    };
    load();
    return () => {
      alive = false;
    };
  }, [filters]);

  useVisibleInterval(() => {
    api
      .redditAutomation(filters)
      .then((data) => {
        setSummary(data);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load Reddit automation analytics.");
      });
  }, 15_000);

  const accounts = summary?.accounts || [];

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Reddit Automation"
        description="Reddit posting split by automated worker output and manually recorded posts."
      />

      <Card className="p-4">
        <div className="grid gap-3 md:grid-cols-5">
          <div>
            <FieldLabel>Date from</FieldLabel>
            <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </div>
          <div>
            <FieldLabel>Date to</FieldLabel>
            <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </div>
          <div>
            <FieldLabel>Account</FieldLabel>
            <Select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              <option value="">All accounts</option>
              {accounts.map((account) => (
                <option key={account.account_id} value={account.account_id}>
                  {account.username}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel>Subreddit</FieldLabel>
            <Input placeholder="All" value={subreddit} onChange={(event) => setSubreddit(event.target.value)} />
          </div>
          <div>
            <FieldLabel>Status</FieldLabel>
            <Select value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === "ALL" ? "All statuses" : option}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {error && <StateMessage tone="error" title="Automation analytics could not load" description={error} compact />}

      {summary ? (
        <>
          <AutomationHealthBanner summary={summary} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Automated posts" value={summary.total_automated_posts} hint={`${summary.posts_last_day} automated in last 24h`} />
            <MetricCard label="Manual posted" value={summary.manual_posted_posts} hint={`${summary.manual_posts_last_day} manual in last 24h`} />
            <MetricCard label="Total Reddit posted" value={summary.total_reddit_posted_posts} hint={`${summary.posting_now} posting now`} />
            <MetricCard label="Failed attempts" value={summary.failed_attempts} hint={`${summary.total_attempted_replies} attempted replies`} />
          </div>

          <Card className="min-w-0 p-4">
            <SectionHeader
              title="Controlled Auto-Approval"
              description="New Reddit replies can move to approved automatically only when they pass conservative safety and value rules."
            />
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <StatusFact label="Auto-approved today" value={String(summary.auto_approved_today)} />
              <StatusFact
                label="Normal / promo"
                value={`${summary.auto_approved_normal_today} / ${summary.auto_approved_promo_today}`}
              />
              <StatusFact
                label="Daily caps"
                value={`${summary.auto_approval_caps.normal_daily_cap} normal · ${summary.auto_approval_caps.promo_daily_cap} promo`}
              />
            </div>
            <div className="mt-3 text-sm text-muted-foreground">
              Per-subreddit cap: {summary.auto_approval_caps.per_subreddit_daily_cap}/day · minimum value: {summary.auto_approval_caps.normal_min_value} normal, {summary.auto_approval_caps.promo_min_value} promo
            </div>
            {summary.current_state.state === "idle_empty_queue" && summary.auto_approved_today === 0 && (
              <StateMessage
                className="mt-3"
                title="No replies passed auto-approval today"
                description="New drafts that miss value, cap, promo-fit, or risk checks stay pending for manual review."
                compact
              />
            )}
          </Card>

          <Card className="min-w-0 p-4">
            <SectionHeader
              title="Approved Automation Queue"
              description={`${summary.current_state.approved_queue_count} Reddit replies are currently approved for automation.`}
            />
            <QueueTable items={summary.approved_queue} />
          </Card>

          <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
            <Card className="min-w-0 p-4">
              <SectionHeader title="Latest Automated Posts" description="Replies posted by Reddit workers." />
              <AutomationTable items={summary.latest_posts} emptyTitle="No automated posts match these filters." />
            </Card>

            <Card className="min-w-0 p-4">
              <SectionHeader title="Top Subreddits" description="Automated posts by subreddit." />
              <div className="mt-4 space-y-3">
                {summary.top_subreddits.map((item) => (
                  <RatioRow
                    key={item.name}
                    label={`r/${item.name}`}
                    value={item.count}
                    total={Math.max(1, summary.total_automated_posts)}
                  />
                ))}
                {!summary.top_subreddits.length && (
                  <StateMessage title="No subreddit data" description="No automated posts are available for these filters." compact />
                )}
              </div>
            </Card>
          </div>

          <Card className="min-w-0 p-4">
            <SectionHeader title="Latest Manual Posted Replies" description="Replies an operator marked as posted manually." />
            <AutomationTable items={summary.latest_manual_posts} emptyTitle="No manually posted Reddit replies match these filters." />
          </Card>

          <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
            <Card className="min-w-0 p-4">
              <SectionHeader title="Automation Failures" description="Failed worker attempts and their latest errors." />
              <AutomationTable items={summary.latest_failures} emptyTitle="No automation failures match these filters." failureMode />
            </Card>

            <Card className="min-w-0 p-4">
              <SectionHeader title="Reddit Accounts" description={`${summary.active_account_count} active of ${summary.account_count} accounts.`} />
              <div className="mt-4 space-y-3">
                {summary.accounts.map((account) => (
                  <div key={account.account_id} className="rounded-md border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-semibold">u/{account.username}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          Slot {account.profile_index ?? "?"} · {account.proxy_label || "no proxy"} · {account.has_cookies ? "cookies saved" : "no cookies"}
                        </div>
                      </div>
                      <div className="flex flex-wrap justify-end gap-1">
                        <Badge className={account.status === "ACTIVE" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : ""}>
                          {account.status}
                        </Badge>
                        <Badge className={readinessBadgeClass(account.readiness_status)}>
                          {readinessLabel(account.readiness_status)}
                        </Badge>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
                      <div className="flex justify-between gap-3">
                        <span>Last hour</span>
                        <span className="font-medium text-foreground">
                          {account.posts_last_hour} / {account.posts_per_hour_limit}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Last day</span>
                        <span className="font-medium text-foreground">
                          {account.posts_last_day} / {account.posts_per_day_limit}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Cooldown</span>
                        <span className={account.is_in_cooldown ? "font-medium text-warning" : "font-medium text-emerald-700"}>
                          {account.is_in_cooldown ? formatDuration(account.seconds_until_eligible) : "Ready"}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Last action</span>
                        <span className="max-w-[220px] truncate font-medium text-foreground">
                          {account.last_action || "n/a"}
                        </span>
                      </div>
                    </div>
                    {account.readiness_reasons.length > 0 && (
                      <div className="mt-3 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                        <div className="mb-1 font-semibold uppercase text-muted-foreground">Readiness</div>
                        <ul className="space-y-1">
                          {account.readiness_reasons.slice(0, 3).map((reason) => (
                            <li key={reason} className="break-words">{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      )}
    </div>
  );
}

function AutomationHealthBanner({ summary }: { summary: RedditAutomationSummary }) {
  const state = summary.current_state;
  const toneClass =
    state.state === "ready" || state.state === "posting"
      ? "border-emerald-200 bg-emerald-50"
      : state.state === "cooldown" || state.state === "idle_empty_queue"
        ? "border-amber-200 bg-amber-50"
        : "border-red-200 bg-red-50";
  const badgeClass =
    state.state === "ready" || state.state === "posting"
      ? "border-emerald-200 bg-card text-emerald-700"
      : state.state === "cooldown" || state.state === "idle_empty_queue"
        ? "border-amber-200 bg-card text-warning"
        : "border-red-200 bg-card text-danger";

  return (
    <Card className={`p-4 ${toneClass}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={badgeClass}>{state.worker_running ? "Worker active" : "Worker not confirmed"}</Badge>
            <Badge className={badgeClass}>{state.title}</Badge>
          </div>
          <h3 className="mt-3 text-xl font-semibold tracking-tight text-foreground">{state.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{state.detail}</p>
          {state.blockers.length > 0 && (
            <div className="mt-3 rounded-md border border-border bg-card/70 p-3">
              <div className="text-xs font-semibold uppercase text-muted-foreground">Why it is not posting</div>
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                {state.blockers.map((blocker) => (
                  <li key={blocker} className="break-words">{blocker}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="grid shrink-0 gap-3 text-sm sm:grid-cols-2 lg:min-w-[430px]">
          <StatusFact label="Account" value={state.active_account_username ? `u/${state.active_account_username}` : "None"} />
          <StatusFact label="Approved queue" value={String(state.approved_queue_count)} />
          <StatusFact label="Cooldown" value={state.cooldown_seconds > 0 ? formatDuration(state.cooldown_seconds) : "Ready"} />
          <StatusFact label="Last action" value={state.last_action || "n/a"} />
        </div>
      </div>
    </Card>
  );
}

function StatusFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card/70 p-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium text-foreground">{value}</div>
    </div>
  );
}

function readinessLabel(status: string) {
  switch (status) {
    case "ready":
      return "Ready";
    case "cooldown":
      return "Cooldown";
    case "limited":
      return "Limit";
    case "blocked":
      return "Blocked";
    case "disabled":
      return "Disabled";
    case "attention":
      return "Check";
    default:
      return status;
  }
}

function readinessBadgeClass(status: string) {
  switch (status) {
    case "ready":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "cooldown":
    case "limited":
    case "attention":
      return "border-amber-200 bg-amber-50 text-warning";
    case "blocked":
    case "disabled":
      return "border-red-200 bg-red-50 text-danger";
    default:
      return "";
  }
}

function MetricCard({ label, value, hint }: { label: string; value: number | string; hint: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight">{value}</div>
      <div className="mt-2 text-sm text-muted-foreground">{hint}</div>
    </Card>
  );
}

function QueueTable({ items }: { items: RedditAutomationSummary["approved_queue"] }) {
  if (!items.length) {
    return (
      <StateMessage
        className="mt-4"
        title="No approved Reddit replies waiting"
        description="Automation is idle until new Reddit replies are approved."
        compact
      />
    );
  }

  return (
    <TableShell className="mt-4" minWidth={920}>
      <thead className={tableHeadClassName}>
        <tr>
          <th className={tableCellClassName}>Reply</th>
          <th className={tableCellClassName}>Subreddit</th>
          <th className={tableCellClassName}>Status</th>
          <th className={tableCellClassName}>Attempts</th>
          <th className={tableCellClassName}>Target</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.reply_id} className={tableRowClassName}>
            <td className={tableCellClassName}>
              <div className="font-medium">#{item.reply_id}</div>
              <div className="mt-1 max-w-lg text-xs text-muted-foreground">{item.reply_text_preview}</div>
            </td>
            <td className={tableCellClassName}>{item.subreddit ? `r/${item.subreddit}` : "n/a"}</td>
            <td className={tableCellClassName}>
              <Badge>{item.status}</Badge>
            </td>
            <td className={tableCellClassName}>{item.posting_attempts}</td>
            <td className={tableCellClassName}>
              {item.target_url ? (
                <a className="text-accent underline" href={item.target_url} target="_blank">
                  Open target
                </a>
              ) : (
                "n/a"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </TableShell>
  );
}

function AutomationTable({
  items,
  emptyTitle,
  failureMode = false,
}: {
  items: RedditAutomationSummary["latest_posts"];
  emptyTitle: string;
  failureMode?: boolean;
}) {
  if (!items.length) {
    return <StateMessage className="mt-4" title={emptyTitle} compact />;
  }

  return (
    <TableShell className="mt-4" minWidth={920}>
      <thead className={tableHeadClassName}>
        <tr>
          <th className={tableCellClassName}>Reply</th>
          <th className={tableCellClassName}>Subreddit</th>
          <th className={tableCellClassName}>Account</th>
          <th className={tableCellClassName}>Status</th>
          <th className={tableCellClassName}>Attempts</th>
          <th className={tableCellClassName}>{failureMode ? "Error" : "Posted"}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.reply_id} className={tableRowClassName}>
            <td className={tableCellClassName}>
              <div className="font-medium">#{item.reply_id}</div>
              <div className="mt-1 max-w-md text-xs text-muted-foreground">{item.reply_text_preview}</div>
            </td>
            <td className={tableCellClassName}>{item.subreddit ? `r/${item.subreddit}` : "n/a"}</td>
            <td className={tableCellClassName}>{item.account_username ? `u/${item.account_username}` : "n/a"}</td>
            <td className={tableCellClassName}>
              <Badge>{item.status}</Badge>
            </td>
            <td className={tableCellClassName}>{item.posting_attempts}</td>
            <td className={tableCellClassName}>
              {failureMode ? (
                <div className="max-w-md break-words text-danger">{item.posting_error || "No error recorded"}</div>
              ) : (
                <div>
                  <div>{formatDate(item.posted_at || item.event_time)}</div>
                  {item.posted_url && (
                    <a className="mt-1 block truncate text-xs text-accent underline" href={item.posted_url} target="_blank">
                      Open
                    </a>
                  )}
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </TableShell>
  );
}

function RatioRow({ label, value, total }: { label: string; value: number; total: number }) {
  const width = Math.round((value / total) * 100);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="truncate font-medium">{label}</span>
        <span className="text-muted-foreground">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div className="h-2 rounded-full bg-orange-500" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return "Ready";
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}
