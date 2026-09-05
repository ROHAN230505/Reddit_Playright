"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ProxyItem } from "@/lib/api";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Badge,
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
} from "@/components/legacy-ui";

function relativeTime(value: string | null): string {
  if (!value) return "n/a";
  const diff = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function statusBadge(status: ProxyItem["status"]) {
  if (status === "ACTIVE") return <Badge className="border-emerald-500/20 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">ACTIVE</Badge>;
  if (status === "FAILED") return <Badge className="border-rose-500/20 bg-rose-500/15 text-rose-600 dark:text-rose-400">FAILED</Badge>;
  return <Badge className="border-border bg-muted text-muted-foreground">DISABLED</Badge>;
}

type FormState = {
  label: string;
  scheme: "http" | "https" | "socks5";
  host: string;
  port: string;
  username: string;
  password: string;
  notes: string;
  skip_validation: boolean;
};

const emptyForm = (): FormState => ({
  label: "",
  scheme: "http",
  host: "",
  port: "1080",
  username: "",
  password: "",
  notes: "",
  skip_validation: false,
});

type Notice = { type: "success" | "error"; text: string; id: number };

export default function ProxiesSection() {
  const [proxies, setProxies] = useState<ProxyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notices, setNotices] = useState<Notice[]>([]);
  const noticeId = useRef(0);

  function addNotice(type: "success" | "error", text: string) {
    const id = ++noticeId.current;
    setNotices((prev) => [...prev, { type, text, id }]);
    setTimeout(() => setNotices((prev) => prev.filter((n) => n.id !== id)), 4000);
  }

  async function load() {
    try {
      const data = await api.proxies();
      setProxies(data);
    } catch {
      // silently ignore poll errors
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useVisibleInterval(() => {
    void load();
  }, 30_000);

  function openAdd() {
    setEditId(null);
    setForm(emptyForm());
    setFormError("");
    setFormOpen(true);
  }

  function openEdit(proxy: ProxyItem) {
    setEditId(proxy.id);
    setForm({
      label: proxy.label,
      scheme: proxy.scheme,
      host: proxy.host,
      port: String(proxy.port),
      username: proxy.username ?? "",
      password: "",
      notes: proxy.notes ?? "",
      skip_validation: false,
    });
    setFormError("");
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditId(null);
    setFormError("");
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setFormError("");
    try {
      if (editId !== null) {
        const body: Parameters<typeof api.updateProxy>[1] = {
          label: form.label,
          scheme: form.scheme,
          host: form.host,
          port: Number(form.port),
          notes: form.notes || undefined,
        };
        if (form.username) body.username = form.username;
        if (form.password) body.password = form.password;
        await api.updateProxy(editId, body);
        addNotice("success", "Proxy updated");
        closeForm();
        await load();
      } else {
        const result = await api.createProxy({
          label: form.label,
          scheme: form.scheme,
          host: form.host,
          port: Number(form.port),
          username: form.username || undefined,
          password: form.password || undefined,
          notes: form.notes || undefined,
          skip_validation: form.skip_validation,
        });
        if (!result.ok) {
          // Parse structured 422 detail
          const body = result.data as { detail?: { message?: string; error?: string } };
          const msg = body?.detail?.message ?? body?.detail?.error ?? result.errorText ?? "Unknown error";
          setFormError(msg);
        } else {
          addNotice("success", "Proxy added");
          closeForm();
          await load();
        }
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save proxy");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleValidate(id: number) {
    try {
      const result = await api.validateProxy(id);
      if (result.ok) {
        addNotice("success", `Validated — IP: ${result.ip ?? "unknown"}`);
      } else {
        addNotice("error", `Validation failed: ${result.error ?? "unknown error"}`);
      }
      await load();
    } catch (err) {
      addNotice("error", err instanceof Error ? err.message : "Validation request failed");
    }
  }

  async function handleDelete(proxy: ProxyItem) {
    if (!window.confirm(`Delete proxy "${proxy.label}"?`)) return;
    try {
      await api.deleteProxy(proxy.id);
      addNotice("success", "Proxy deleted");
      await load();
    } catch (err) {
      addNotice("error", err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-5">
      {/* Toast notices */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {notices.map((n) => (
          <div
            key={n.id}
            className={`rounded-md border px-4 py-3 text-sm shadow-soft ${
              n.type === "success"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "border-destructive/30 bg-destructive/10 text-destructive"
            }`}
          >
            {n.text}
          </div>
        ))}
      </div>

      <SectionHeader
        title="Proxies"
        description="Manage outbound proxies used by posting accounts."
        actions={<Button onClick={openAdd}>Add proxy</Button>}
      />

      {formOpen && (
        <Card className="p-4">
          <h3 className="mb-4 font-semibold text-foreground">{editId !== null ? "Edit proxy" : "Add proxy"}</h3>
          <form onSubmit={handleSubmit} className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Label *</label>
                <Input value={form.label} onChange={(e) => set("label", e.target.value)} required placeholder="residential-1" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Scheme</label>
                <Select value={form.scheme} onChange={(e) => set("scheme", e.target.value as FormState["scheme"])}>
                  <option value="http">http</option>
                  <option value="https">https</option>
                  <option value="socks5">socks5</option>
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Host *</label>
                <Input value={form.host} onChange={(e) => set("host", e.target.value)} required placeholder="1.2.3.4" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Port *</label>
                <Input type="number" min={1} max={65535} value={form.port} onChange={(e) => set("port", e.target.value)} required />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Username (optional)</label>
                <Input value={form.username} onChange={(e) => set("username", e.target.value)} placeholder="proxyuser" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Password (optional)</label>
                <Input type="password" value={form.password} onChange={(e) => set("password", e.target.value)} placeholder={editId !== null ? "leave blank to keep" : ""} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">Notes (optional)</label>
              <Textarea value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="e.g. US residential, provider XYZ" className="min-h-16" />
            </div>
            {editId === null && (
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input type="checkbox" checked={form.skip_validation} onChange={(e) => set("skip_validation", e.target.checked)} />
                Skip live validation (save with status DISABLED until manually validated)
              </label>
            )}
            {formError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{formError}</div>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={submitting}>{submitting ? "Saving…" : "Save"}</Button>
              <Button type="button" variant="outline" onClick={closeForm}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      <Card className="overflow-hidden">
        {loading && !proxies.length ? (
          <div className="p-4">
            <StateMessage title="Loading proxies..." description="Checking saved proxy inventory." compact />
          </div>
        ) : !proxies.length ? (
          <div className="p-4">
            <StateMessage title="No proxies yet" description="Add a proxy to assign to posting accounts." />
          </div>
        ) : (
          <TableShell minWidth={900}>
              <thead className={tableHeadClassName}>
                <tr>
                  <th className={tableCellClassName}>Label</th>
                  <th className={tableCellClassName}>Address</th>
                  <th className={tableCellClassName}>Status</th>
                  <th className={tableCellClassName}>Accounts</th>
                  <th className={tableCellClassName}>Ext IP</th>
                  <th className={tableCellClassName}>Last checked</th>
                  <th className={tableCellClassName}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {proxies.map((proxy) => (
                  <tr key={proxy.id} className={tableRowClassName}>
                    <td className={`${tableCellClassName} font-medium`}>{proxy.label}</td>
                    <td className={`${tableCellClassName} font-mono text-xs`}>
                      {proxy.scheme}://{proxy.host}:{proxy.port}
                    </td>
                    <td className={tableCellClassName}>{statusBadge(proxy.status)}</td>
                    <td className={tableCellClassName}>{proxy.account_count}</td>
                    <td className={`${tableCellClassName} font-mono text-xs`}>{proxy.last_check_ip ?? "—"}</td>
                    <td className={tableCellClassName}>
                      <div>{relativeTime(proxy.last_checked_at)}</div>
                      {proxy.last_check_error && (
                        <div className="mt-0.5 max-w-xs truncate text-xs text-destructive" title={proxy.last_check_error}>
                          {proxy.last_check_error}
                        </div>
                      )}
                    </td>
                    <td className={tableCellClassName}>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" onClick={() => handleValidate(proxy.id)}>
                          Validate
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEdit(proxy)}>
                          Edit
                        </Button>
                        <span title={proxy.account_count > 0 ? `Cannot delete — ${proxy.account_count} account(s) still assigned` : ""}>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={proxy.account_count > 0}
                            onClick={() => handleDelete(proxy)}
                          >
                            Delete
                          </Button>
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
          </TableShell>
        )}
      </Card>

      <div className="text-xs text-muted-foreground">
        Auto-refreshes every 5 seconds. Last checked: {formatDate(new Date().toISOString())}
      </div>
    </div>
  );
}
