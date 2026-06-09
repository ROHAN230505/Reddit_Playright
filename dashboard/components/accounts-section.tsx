"use client";

import { useEffect, useRef, useState } from "react";
import { api, type AccountActivity, type ProxyItem, type RedditAccountItem } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  Badge,
  Button,
  Card,
  Input,
  SectionHeader,
  Select,
  StateMessage,
  TableShell,
  Textarea,
  tableCellClassName,
  tableHeadClassName,
  tableRowClassName,
} from "@/components/ui";

const PROFILE_SLOT_COUNT = 6;

function relativeTime(value: string | null): string {
  if (!value) return "n/a";
  const diff = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return "ready";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m`;
  return `${Math.ceil(seconds / 3600)}h`;
}

function statusBadge(status: RedditAccountItem["status"]) {
  switch (status) {
    case "ACTIVE":
      return <Badge className="bg-emerald-500/15 text-emerald-700 border-emerald-200">ACTIVE</Badge>;
    case "NEW":
    case "VERIFYING":
      return <Badge className="bg-amber-500/15 text-amber-700 border-amber-200">{status}</Badge>;
    case "NEEDS_REAUTH":
      return <Badge className="bg-amber-500/15 text-amber-700 border-amber-200">NEEDS_REAUTH</Badge>;
    case "FAILED":
      return <Badge className="bg-rose-500/15 text-rose-700 border-rose-200">FAILED</Badge>;
    case "DISABLED":
      return <Badge className="bg-zinc-500/15 text-zinc-600 border-zinc-200">DISABLED</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
}

type AddFormState = {
  username: string;
  password: string;
  totp_secret: string;
  proxy_id: string; // "" means none
  platform: "reddit" | "glp" | "chan";
  // advanced
  profile_index: string; // "" means auto
  posts_per_hour_limit: string;
  posts_per_day_limit: string;
  min_seconds_between_posts: string;
  max_seconds_between_posts: string;
};

type EditFormState = {
  password: string;
  totp_secret: string;
  proxy_id: string;
  is_enabled: boolean;
  // advanced
  profile_index: string; // "" means no change
  posts_per_hour_limit: string;
  posts_per_day_limit: string;
  min_seconds_between_posts: string;
  max_seconds_between_posts: string;
};

type VerifyPhase =
  | { kind: "idle" }
  | { kind: "polling"; accountId: number; username: string; status: RedditAccountItem["status"] }
  | { kind: "done"; account: RedditAccountItem };

export default function AccountsSection() {
  const [accounts, setAccounts] = useState<RedditAccountItem[]>([]);
  const [proxies, setProxies] = useState<ProxyItem[]>([]);
  const [activity, setActivity] = useState<Record<number, AccountActivity>>({});
  const [loading, setLoading] = useState(true);
  const [formMode, setFormMode] = useState<"none" | "add" | "edit">("none");
  const [editId, setEditId] = useState<number | null>(null);
  const [manualLoginAccount, setManualLoginAccount] = useState<RedditAccountItem | null>(null);
  const [addForm, setAddForm] = useState<AddFormState>({ username: "", password: "", totp_secret: "", proxy_id: "", platform: "reddit", profile_index: "", posts_per_hour_limit: "", posts_per_day_limit: "", min_seconds_between_posts: "", max_seconds_between_posts: "" });
  const [editForm, setEditForm] = useState<EditFormState>({ password: "", totp_secret: "", proxy_id: "", is_enabled: true, profile_index: "", posts_per_hour_limit: "", posts_per_day_limit: "", min_seconds_between_posts: "", max_seconds_between_posts: "" });
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [verifyPhase, setVerifyPhase] = useState<VerifyPhase>({ kind: "idle" });
  const pollRef = useRef<number | null>(null);
  const pollStartRef = useRef<number>(0);

  async function loadAll() {
    try {
      const [health, prxs] = await Promise.all([api.accountsHealth(), api.proxies()]);
      setAccounts(health.accounts);
      setProxies(prxs);
      setActivity(health.activity);
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    const timer = window.setInterval(loadAll, 3000);
    return () => {
      window.clearInterval(timer);
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startVerifyPolling(accountId: number, username: string) {
    pollStartRef.current = Date.now();
    setVerifyPhase({ kind: "polling", accountId, username, status: "NEW" });
    pollRef.current = window.setInterval(async () => {
      const elapsed = Date.now() - pollStartRef.current;
      if (elapsed > 5 * 60 * 1000) {
        stopPolling();
        setVerifyPhase({ kind: "done", account: { id: accountId, username, status: "VERIFYING", has_totp: false, proxy_id: null, proxy_label: null, is_enabled: true, last_login_at: null, last_seen_at: null, last_action: "timeout", last_error: "Verification taking longer than expected — see Live tab", user_data_dir: null, created_at: new Date().toISOString() } });
        return;
      }
      try {
        const acct = await api.account(accountId);
        setVerifyPhase((prev) => prev.kind === "polling" ? { ...prev, status: acct.status } : prev);
        if (acct.status === "ACTIVE" || acct.status === "FAILED" || acct.status === "NEEDS_REAUTH") {
          stopPolling();
          setVerifyPhase({ kind: "done", account: acct });
          await loadAll();
        }
      } catch {
        // keep polling
      }
    }, 1500);
  }

  function setAddField<K extends keyof AddFormState>(key: K, value: AddFormState[K]) {
    setAddForm((prev) => ({ ...prev, [key]: value }));
  }

  function setEditField<K extends keyof EditFormState>(key: K, value: EditFormState[K]) {
    setEditForm((prev) => ({ ...prev, [key]: value }));
  }

  function openAdd() {
    stopPolling();
    setFormMode("add");
    setAddForm({ username: "", password: "", totp_secret: "", proxy_id: "", platform: "reddit", profile_index: "", posts_per_hour_limit: "", posts_per_day_limit: "", min_seconds_between_posts: "", max_seconds_between_posts: "" });
    setFormError("");
    setVerifyPhase({ kind: "idle" });
  }

  function openEdit(account: RedditAccountItem) {
    setFormMode("edit");
    setEditId(account.id);
    setEditForm({
      password: "",
      totp_secret: "",
      proxy_id: account.proxy_id != null ? String(account.proxy_id) : "",
      is_enabled: account.is_enabled,
      profile_index: account.profile_index != null ? String(account.profile_index) : "",
      posts_per_hour_limit: account.posts_per_hour_limit != null ? String(account.posts_per_hour_limit) : "",
      posts_per_day_limit: account.posts_per_day_limit != null ? String(account.posts_per_day_limit) : "",
      min_seconds_between_posts: account.min_seconds_between_posts != null ? String(account.min_seconds_between_posts) : "",
      max_seconds_between_posts: account.max_seconds_between_posts != null ? String(account.max_seconds_between_posts) : "",
    });
    setFormError("");
  }

  function closeForm() {
    setFormMode("none");
    setEditId(null);
    setFormError("");
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setFormError("");
    try {
      const body: Parameters<typeof api.createAccount>[0] = {
        username: addForm.username.trim(),
        password: addForm.password,
      };
      if (addForm.totp_secret.trim()) body.totp_secret = addForm.totp_secret.trim();
      if (addForm.proxy_id) body.proxy_id = Number(addForm.proxy_id);
      if (addForm.platform && addForm.platform !== "reddit") body.platform = addForm.platform;
      if (addForm.profile_index !== "") body.profile_index = Number(addForm.profile_index);
      if (addForm.posts_per_hour_limit !== "") body.posts_per_hour_limit = Number(addForm.posts_per_hour_limit);
      if (addForm.posts_per_day_limit !== "") body.posts_per_day_limit = Number(addForm.posts_per_day_limit);
      if (addForm.min_seconds_between_posts !== "") body.min_seconds_between_posts = Number(addForm.min_seconds_between_posts);
      if (addForm.max_seconds_between_posts !== "") body.max_seconds_between_posts = Number(addForm.max_seconds_between_posts);
      const newAccount = await api.createAccount(body);
      startVerifyPolling(newAccount.id, newAccount.username);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to add account");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (editId === null) return;
    setSubmitting(true);
    setFormError("");
    try {
      const body: Parameters<typeof api.updateAccount>[1] = {};
      if (editForm.password) body.password = editForm.password;
      if (editForm.totp_secret) body.totp_secret = editForm.totp_secret;
      body.proxy_id = editForm.proxy_id ? Number(editForm.proxy_id) : null;
      body.is_enabled = editForm.is_enabled;
      if (editForm.profile_index !== "") body.profile_index = Number(editForm.profile_index);
      if (editForm.posts_per_hour_limit !== "") body.posts_per_hour_limit = Number(editForm.posts_per_hour_limit);
      if (editForm.posts_per_day_limit !== "") body.posts_per_day_limit = Number(editForm.posts_per_day_limit);
      if (editForm.min_seconds_between_posts !== "") body.min_seconds_between_posts = Number(editForm.min_seconds_between_posts);
      if (editForm.max_seconds_between_posts !== "") body.max_seconds_between_posts = Number(editForm.max_seconds_between_posts);
      await api.updateAccount(editId, body);
      closeForm();
      await loadAll();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to update account");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReverify(id: number) {
    try {
      await api.reverifyAccount(id);
      await loadAll();
    } catch (err) {
      console.error(err);
    }
  }

  async function handleToggleEnabled(account: RedditAccountItem) {
    try {
      await api.updateAccount(account.id, { is_enabled: !account.is_enabled });
      await loadAll();
    } catch (err) {
      console.error(err);
    }
  }

  const selectedProxy = proxies.find((p) => String(p.id) === addForm.proxy_id);
  const activeAccounts = accounts.filter((account) => account.status === "ACTIVE" && account.is_enabled).length;
  const cooldownAccounts = accounts.filter((account) => activity[account.id]?.is_in_cooldown).length;
  const limitedAccounts = accounts.filter((account) => {
    const row = activity[account.id];
    return row?.is_at_hourly_limit || row?.is_at_daily_limit;
  }).length;
  const failedAccounts = accounts.filter((account) => account.status === "FAILED" || account.last_error || activity[account.id]?.last_failed_post).length;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Accounts"
        description="Add and manage posting accounts. Health and activity refresh every 3 seconds."
        actions={formMode === "none" ? <Button onClick={openAdd}>Add account</Button> : null}
      />

      {/* Add form */}
      {formMode === "add" && verifyPhase.kind === "idle" && (
        <Card className="p-4">
          <h3 className="mb-4 font-semibold">Add account</h3>
          <form onSubmit={handleAdd} className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted">Username *</label>
                <Input value={addForm.username} onChange={(e) => setAddField("username", e.target.value)} required placeholder="redditbot01" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted">Password *</label>
                <Input type="password" value={addForm.password} onChange={(e) => setAddField("password", e.target.value)} required />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-muted">Platform *</label>
              <Select
                value={addForm.platform}
                onChange={(e) => setAddField("platform", e.target.value as "reddit" | "glp" | "chan")}
              >
                <option value="reddit">Reddit</option>
                <option value="glp">Godlike Productions</option>
                <option value="chan">4chan</option>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-muted">
                2FA shared secret (base32) — TOTP code generated automatically
              </label>
              <Textarea
                value={addForm.totp_secret}
                onChange={(e) => setAddField("totp_secret", e.target.value)}
                placeholder="Optional. Paste your TOTP base32 secret here."
                className="min-h-16"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-muted">Proxy</label>
              <Select value={addForm.proxy_id} onChange={(e) => setAddField("proxy_id", e.target.value)}>
                <option value="">— none —</option>
                {proxies.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.label} — {p.host}:{p.port} — {p.account_count} account{p.account_count !== 1 ? "s" : ""}
                  </option>
                ))}
              </Select>
              {selectedProxy && selectedProxy.account_count >= 1 && (
                <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-warning">
                  This proxy already has {selectedProxy.account_count} account(s). One account per proxy is recommended for stealth — pick a different one if you can.
                </div>
              )}
            </div>
            <details className="rounded-md border border-slate-200 px-3 py-2">
              <summary className="cursor-pointer text-xs font-semibold uppercase text-muted select-none">
                Rate limits &amp; profile (advanced)
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Profile slot (auto)</label>
                  <Select value={addForm.profile_index} onChange={(e) => setAddField("profile_index", e.target.value)}>
                    <option value="">— auto (round-robin) —</option>
                    {Array.from({ length: PROFILE_SLOT_COUNT }, (_, i) => (
                      <option key={i} value={String(i)}>Slot {i}</option>
                    ))}
                  </Select>
                </div>
                <div />
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Posts / hour</label>
                  <Input
                    type="number"
                    min={1} max={200}
                    value={addForm.posts_per_hour_limit}
                    onChange={(e) => setAddField("posts_per_hour_limit", e.target.value)}
                    placeholder="4"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Posts / day</label>
                  <Input
                    type="number"
                    min={1} max={2000}
                    value={addForm.posts_per_day_limit}
                    onChange={(e) => setAddField("posts_per_day_limit", e.target.value)}
                    placeholder="30"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Min seconds between posts</label>
                  <Input
                    type="number"
                    min={10} max={86400}
                    value={addForm.min_seconds_between_posts}
                    onChange={(e) => setAddField("min_seconds_between_posts", e.target.value)}
                    placeholder="300"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Max seconds between posts</label>
                  <Input
                    type="number"
                    min={10} max={86400}
                    value={addForm.max_seconds_between_posts}
                    onChange={(e) => setAddField("max_seconds_between_posts", e.target.value)}
                    placeholder="900"
                  />
                </div>
              </div>
            </details>
            {formError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{formError}</div>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={submitting}>{submitting ? "Adding…" : "Add and verify"}</Button>
              <Button type="button" variant="secondary" onClick={closeForm}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {/* Verify polling UI */}
      {formMode === "add" && verifyPhase.kind === "polling" && (
        <Card className="p-4">
          <h3 className="mb-3 font-semibold">Verifying account…</h3>
          <div className="flex items-center gap-3 text-sm">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span>
              Verifying <strong>{verifyPhase.username}</strong>… status=
              <strong>{verifyPhase.status}</strong>
            </span>
          </div>
          <p className="mt-2 text-xs text-muted">
            The worker will pick this up within ~60s and transition through NEW → VERIFYING → ACTIVE / FAILED / NEEDS_REAUTH.
          </p>
        </Card>
      )}

      {/* Verify done UI */}
      {formMode === "add" && verifyPhase.kind === "done" && (
        <Card className="p-4">
          <h3 className="mb-3 font-semibold">Verification result</h3>
          {verifyPhase.account.status === "ACTIVE" && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              <strong>{verifyPhase.account.username}</strong> is now <strong>ACTIVE</strong>. Ready to post.
            </div>
          )}
          {verifyPhase.account.status === "FAILED" && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">
              <strong>FAILED</strong> — {verifyPhase.account.last_error ?? "Unknown error"}
            </div>
          )}
          {verifyPhase.account.status === "NEEDS_REAUTH" && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-warning">
              <strong>NEEDS_REAUTH</strong> — {verifyPhase.account.last_error ?? "Re-authentication required"}
            </div>
          )}
          {verifyPhase.account.last_action === "timeout" && (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-warning">
              {verifyPhase.account.last_error}
            </div>
          )}
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() => {
                setVerifyPhase({ kind: "idle" });
                setAddForm({ username: "", password: "", totp_secret: "", proxy_id: "", platform: "reddit", profile_index: "", posts_per_hour_limit: "", posts_per_day_limit: "", min_seconds_between_posts: "", max_seconds_between_posts: "" });
                setFormError("");
              }}
            >
              Add another
            </Button>
          </div>
        </Card>
      )}

      {/* Edit form */}
      {formMode === "edit" && editId !== null && (
        <Card className="p-4">
          <h3 className="mb-4 font-semibold">Edit account</h3>
          <form onSubmit={handleEdit} className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted">New password</label>
                <Input type="password" value={editForm.password} onChange={(e) => setEditField("password", e.target.value)} placeholder="leave blank to keep" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted">New TOTP secret</label>
                <Input value={editForm.totp_secret} onChange={(e) => setEditField("totp_secret", e.target.value)} placeholder="leave blank to keep" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-muted">Proxy</label>
              <Select value={editForm.proxy_id} onChange={(e) => setEditField("proxy_id", e.target.value)}>
                <option value="">— none —</option>
                {proxies.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.label} — {p.host}:{p.port} — {p.account_count} account{p.account_count !== 1 ? "s" : ""}
                  </option>
                ))}
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editForm.is_enabled} onChange={(e) => setEditField("is_enabled", e.target.checked)} />
              Account enabled
            </label>
            <details className="rounded-md border border-slate-200 px-3 py-2">
              <summary className="cursor-pointer text-xs font-semibold uppercase text-muted select-none">
                Rate limits &amp; profile (advanced)
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Profile slot (leave blank to keep)</label>
                  <Select value={editForm.profile_index} onChange={(e) => setEditField("profile_index", e.target.value)}>
                    <option value="">— no change —</option>
                    {Array.from({ length: PROFILE_SLOT_COUNT }, (_, i) => (
                      <option key={i} value={String(i)}>Slot {i}</option>
                    ))}
                  </Select>
                </div>
                <div />
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Posts / hour</label>
                  <Input
                    type="number"
                    min={1} max={200}
                    value={editForm.posts_per_hour_limit}
                    onChange={(e) => setEditField("posts_per_hour_limit", e.target.value)}
                    placeholder="leave blank to keep"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Posts / day</label>
                  <Input
                    type="number"
                    min={1} max={2000}
                    value={editForm.posts_per_day_limit}
                    onChange={(e) => setEditField("posts_per_day_limit", e.target.value)}
                    placeholder="leave blank to keep"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Min seconds between posts</label>
                  <Input
                    type="number"
                    min={10} max={86400}
                    value={editForm.min_seconds_between_posts}
                    onChange={(e) => setEditField("min_seconds_between_posts", e.target.value)}
                    placeholder="leave blank to keep"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase text-muted">Max seconds between posts</label>
                  <Input
                    type="number"
                    min={10} max={86400}
                    value={editForm.max_seconds_between_posts}
                    onChange={(e) => setEditField("max_seconds_between_posts", e.target.value)}
                    placeholder="leave blank to keep"
                  />
                </div>
              </div>
            </details>
            {formError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">{formError}</div>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
              <Button type="button" variant="secondary" onClick={closeForm}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {/* Cookie paste modal */}
      {manualLoginAccount && (
        <CookiePasteCard
          account={manualLoginAccount}
          onClose={() => setManualLoginAccount(null)}
          onSaved={(updated) => {
            setAccounts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
            setManualLoginAccount(updated);
          }}
        />
      )}

      {/* Accounts table */}
      {accounts.length > 0 && (
        <div className="grid gap-3 md:grid-cols-4">
          <Card className="p-4">
            <div className="text-xs uppercase text-muted">Active accounts</div>
            <div className="mt-1 text-2xl font-semibold">{activeAccounts}/{accounts.length}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase text-muted">In cooldown</div>
            <div className="mt-1 text-2xl font-semibold">{cooldownAccounts}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase text-muted">At limits</div>
            <div className="mt-1 text-2xl font-semibold">{limitedAccounts}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase text-muted">Need attention</div>
            <div className="mt-1 text-2xl font-semibold">{failedAccounts}</div>
          </Card>
        </div>
      )}

      <Card className="overflow-hidden">
        {loading && !accounts.length ? (
          <div className="p-4">
            <StateMessage title="Loading accounts..." description="Fetching account health and usage." compact />
          </div>
        ) : !accounts.length ? (
          <div className="p-4">
            <StateMessage title="No accounts yet" description="Add an account to start posting and tracking health." />
          </div>
        ) : (
          <TableShell minWidth={1520}>
              <thead className={tableHeadClassName}>
                <tr>
                  <th className={tableCellClassName}>Username</th>
                  <th className={tableCellClassName}>Status</th>
                  <th className={tableCellClassName}>Health</th>
                  <th className={tableCellClassName}>Usage</th>
                  <th className={tableCellClassName}>Cooldown</th>
                  <th className={tableCellClassName}>Proxy</th>
                  <th className={tableCellClassName}>Profile</th>
                  <th className={tableCellClassName}>Rate limits</th>
                  <th className={tableCellClassName}>Last post</th>
                  <th className={tableCellClassName}>Last seen</th>
                  <th className={tableCellClassName}>Failed post</th>
                  <th className={tableCellClassName}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => {
                  const row = activity[account.id];
                  const proxy = proxies.find((item) => item.id === account.proxy_id);
                  const hasAttention = account.status === "FAILED" || account.status === "NEEDS_REAUTH" || !!account.last_error || !!row?.last_failed_post;
                  return (
                  <tr key={account.id} className={tableRowClassName}>
                    <td className={`${tableCellClassName} font-medium`}>
                      <span
                        className={
                          "mr-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide " +
                          (account.platform === "glp"
                            ? "bg-purple-100 text-purple-700"
                            : account.platform === "chan"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-orange-100 text-orange-700")
                        }
                        title={`platform=${account.platform ?? "reddit"}`}
                      >
                        {account.platform === "glp"
                          ? "GLP"
                          : account.platform === "chan"
                          ? "4CH"
                          : "RDT"}
                      </span>
                      {account.username}
                      {!account.is_enabled && (
                        <span className="ml-2 text-xs text-muted">(disabled)</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>{statusBadge(account.status)}</td>
                    <td className={tableCellClassName}>
                      {hasAttention ? (
                        <Badge className="border-rose-200 bg-rose-50 text-rose-700">Attention</Badge>
                      ) : row?.is_in_cooldown ? (
                        <Badge className="border-amber-200 bg-amber-50 text-amber-700">Cooling</Badge>
                      ) : row?.is_at_hourly_limit || row?.is_at_daily_limit ? (
                        <Badge className="border-amber-200 bg-amber-50 text-amber-700">Limited</Badge>
                      ) : account.is_enabled ? (
                        <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Ready</Badge>
                      ) : (
                        <Badge className="border-zinc-200 bg-zinc-50 text-zinc-600">Disabled</Badge>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      {row ? (
                        <div className="font-mono text-xs text-slate-600">
                          <div>{row.posts_last_hour}/{row.posts_per_hour_limit} hr</div>
                          <div>{row.posts_last_day}/{row.posts_per_day_limit} day</div>
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      {row?.is_in_cooldown ? (
                        <div>
                          <div className="font-medium text-amber-700">{formatDuration(row.seconds_until_eligible)}</div>
                          <div className="text-xs text-muted">{formatDate(row.next_eligible_at)}</div>
                        </div>
                      ) : (
                        <span className="text-emerald-700">Ready</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      <div>{account.proxy_label ?? <span className="text-muted">— none —</span>}</div>
                      {proxy && (
                        <div
                          className={
                            "mt-1 text-xs " +
                            (proxy.status === "ACTIVE"
                              ? "text-emerald-700"
                              : proxy.status === "FAILED"
                              ? "text-danger"
                              : "text-muted")
                          }
                          title={proxy.last_check_error ?? undefined}
                        >
                          {proxy.status.toLowerCase()}
                          {proxy.last_check_ip ? ` · ${proxy.last_check_ip}` : ""}
                        </div>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      {account.profile_summary ? (
                        <span
                          className="font-mono text-xs text-slate-600"
                          title={account.profile_summary}
                        >
                          {/* Show "slot N · browser summary" truncated */}
                          slot {account.profile_index ?? "?"} · {account.profile_summary.replace(/^slot \d+:\s*/, "").split(",").slice(0, 2).join(" ")}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      {account.posts_per_hour_limit != null ? (
                        <span className="font-mono text-xs text-slate-600">
                          {account.posts_per_hour_limit}/hr · {account.posts_per_day_limit}/day · {Math.round((account.min_seconds_between_posts ?? 300) / 60)}-{Math.round((account.max_seconds_between_posts ?? 900) / 60)}min
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      {row?.last_posted_at ? (
                        <div>
                          <div>{relativeTime(row.last_posted_at)}</div>
                          <div className="max-w-[160px] truncate text-xs text-muted" title={row.recent_posts[0]?.reply_text_preview}>
                            {row.recent_posts[0]?.subreddit ? `r/${row.recent_posts[0].subreddit}` : row.recent_posts[0]?.reply_text_preview}
                          </div>
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>{relativeTime(account.last_seen_at)}</td>
                    <td className={`${tableCellClassName} max-w-[220px]`}>
                      {row?.last_failed_post ? (
                        <div className="truncate text-danger" title={row.last_failed_post.error}>
                          {row.last_failed_post.error}
                        </div>
                      ) : account.last_error ? (
                        <div className="truncate text-danger" title={account.last_error}>
                          {account.last_error}
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="secondary" onClick={() => handleReverify(account.id)}>
                          Reverify
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => openEdit(account)}>
                          Edit
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => handleToggleEnabled(account)}>
                          {account.is_enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => setManualLoginAccount(account)}>
                          {account.has_cookies ? "Cookies ✓" : "Paste cookies"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                )})}
              </tbody>
          </TableShell>
        )}
      </Card>

      <div className="text-xs text-muted">
        Added: {formatDate(accounts[0]?.created_at ?? null)}. Accounts auto-refresh every 3s.
      </div>
    </div>
  );
}

function CookiePasteCard({
  account,
  onClose,
  onSaved,
}: {
  account: RedditAccountItem;
  onClose: () => void;
  onSaved: (updated: RedditAccountItem) => void;
}) {
  const [raw, setRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit() {
    setError(null);
    setSuccess(null);
    if (!raw.trim()) {
      setError("Paste a cookie value, header string, or JSON export first.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.uploadCookies(account.id, raw);
      if (!result.ok) {
        let msg = result.errorText || `HTTP ${result.status}`;
        try {
          const body = JSON.parse(result.errorText);
          if (typeof body.detail === "string") msg = body.detail;
        } catch {}
        setError(msg);
        return;
      }
      setSuccess("Cookies saved. Status reset to NEW; the worker will pick this up on its next refresh tick.");
      setRaw("");
      onSaved(result.data);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleClear() {
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const updated = await api.clearCookies(account.id);
      setSuccess("Cookies cleared.");
      onSaved(updated);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <h3 className="font-semibold">Paste session cookie — u/{account.username}</h3>
        <Button size="sm" variant="secondary" onClick={onClose}>Close</Button>
      </div>
      <p className="mt-2 text-sm text-muted">
        Reddit&apos;s login page hard-blocks headless browsers. Skip it: log into reddit.com in
        your normal browser (ideally <strong>through this account&apos;s assigned proxy</strong> so the IP origin
        matches what the worker uses), then paste the <code>reddit_session</code> cookie below.
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted">
        <li>Easiest: <strong>DevTools → Application → Cookies → reddit.com → copy <code>reddit_session</code></strong> value, paste below.</li>
        <li>Or paste a JSON array exported from the &ldquo;Cookie-Editor&rdquo; / &ldquo;EditThisCookie&rdquo; Chrome extension.</li>
        <li>Or paste a full <code>name=value; name=value</code> string copied from DevTools.</li>
      </ul>
      <Textarea
        className="mt-3 min-h-[140px] font-mono text-xs"
        placeholder='reddit_session value, OR "name=value; name=value", OR Cookie-Editor JSON array'
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        disabled={submitting}
      />
      {error && (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-danger">
          {error}
        </div>
      )}
      {success && (
        <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {success}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Saving…" : "Save cookies"}
        </Button>
        {account.has_cookies && (
          <Button variant="secondary" onClick={handleClear} disabled={submitting}>
            Clear stored cookies
          </Button>
        )}
        <span className="text-xs text-muted">
          {account.has_cookies
            ? `Stored ${account.cookies_set_at ? new Date(account.cookies_set_at).toLocaleString() : ""}`
            : "No cookies stored yet."}
        </span>
      </div>
      <details className="mt-4 text-xs text-muted">
        <summary className="cursor-pointer">CLI fallback</summary>
        <p className="mt-1">If you&apos;d rather skip cookie paste, run a headed login on a machine with a display:</p>
        <pre className="mt-1 overflow-x-auto rounded-md bg-slate-900 px-3 py-2 text-xs text-emerald-300">
          {`python -m playwright_worker login --account ${account.id}`}
        </pre>
      </details>
    </Card>
  );
}
