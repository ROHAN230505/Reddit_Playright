"use client";

import { useEffect, useState } from "react";
import { api, type BrandConfig } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, SectionHeader, Textarea } from "@/components/legacy-ui";

type FormState = {
  name: string;
  mention: string;
  aliases: string;
  one_liner: string;
  topics: string;
  promo_ratio: string;
  salesy_phrases: string;
  example_mentions: string;
  subreddits: string;
  is_enabled: boolean;
  is_active: boolean;
};

const EMPTY_FORM: FormState = {
  name: "",
  mention: "",
  aliases: "",
  one_liner: "",
  topics: "",
  promo_ratio: "",
  salesy_phrases: "",
  example_mentions: "",
  subreddits: "",
  is_enabled: true,
  is_active: false,
};

function lines(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function fromBrand(brand: BrandConfig): FormState {
  return {
    name: brand.name || "",
    mention: brand.mention || "",
    aliases: (brand.aliases || []).join("\n"),
    one_liner: brand.one_liner || "",
    topics: (brand.topics || []).join("\n"),
    promo_ratio: brand.promo_ratio == null ? "" : String(brand.promo_ratio),
    salesy_phrases: (brand.salesy_phrases || []).join("\n"),
    example_mentions: (brand.example_mentions || []).join("\n"),
    subreddits: (brand.subreddits || []).join("\n"),
    is_enabled: brand.is_enabled !== false,
    is_active: Boolean(brand.is_active),
  };
}

function payloadFromForm(form: FormState) {
  const promo = form.promo_ratio.trim();
  return {
    name: form.name.trim(),
    mention: form.mention.trim(),
    aliases: lines(form.aliases),
    one_liner: form.one_liner.trim(),
    topics: lines(form.topics),
    promo_ratio: promo === "" ? null : Number(promo),
    salesy_phrases: lines(form.salesy_phrases),
    example_mentions: lines(form.example_mentions),
    subreddits: lines(form.subreddits),
    is_enabled: form.is_enabled,
  };
}

export default function BrandSection() {
  const [brands, setBrands] = useState<BrandConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load(selectId?: number | "new" | null) {
    const rows = await api.brands();
    setBrands(rows);
    const nextId =
      selectId === "new"
        ? "new"
        : selectId != null
          ? selectId
          : rows.find((item) => item.is_active)?.id ?? rows[0]?.id ?? null;
    setSelectedId(nextId);
    if (nextId === "new") {
      setForm({ ...EMPTY_FORM });
    } else {
      const selected = rows.find((item) => item.id === nextId) || rows[0] || null;
      setForm(selected ? fromBrand(selected) : { ...EMPTY_FORM });
    }
    return rows;
  }

  useEffect(() => {
    load()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function selectBrand(brand: BrandConfig) {
    setSelectedId(brand.id);
    setForm(fromBrand(brand));
    setError("");
    setNotice("");
  }

  function startNew() {
    setSelectedId("new");
    setForm({ ...EMPTY_FORM });
    setError("");
    setNotice("");
  }

  async function save() {
    if (!form) return;
    if (!form.name.trim() || !form.mention.trim()) {
      setError("Name and mention are required.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const body = payloadFromForm(form);
      const saved =
        selectedId === "new" || selectedId == null
          ? await api.createBrand(body)
          : await api.updateBrandById(selectedId, body);
      await load(saved.id);
      setNotice(
        selectedId === "new"
          ? "Brand created. New drafts in its subreddits will mention this product."
          : "Brand saved. New drafts will use this product and these topics.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function setDefault() {
    if (!form || selectedId === "new" || selectedId == null) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await api.updateBrandById(selectedId, { ...payloadFromForm(form), is_active: true });
      await load(saved.id);
      setNotice("This is now the default brand for GLP, 4chan, and unowned subreddits.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set default");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (selectedId === "new" || selectedId == null) return;
    const current = brands.find((item) => item.id === selectedId);
    if (!current) return;
    if (current.is_active) {
      setError("Set another brand as default before deleting this one.");
      return;
    }
    if (!window.confirm(`Delete ${current.name}? Existing drafts stay, but lose this product tag.`)) {
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.deleteBrand(selectedId);
      await load();
      setNotice("Brand deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading || !form) {
    return <p className="text-sm text-muted-foreground">{error || "Loading brands…"}</p>;
  }

  const selected = brands.find((item) => item.id === selectedId);

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Brands"
        description="Run more than one product at once. Each brand owns its subreddits, topics, and promo mention. Bind posting accounts to a brand so one Reddit login never mixes products. The default brand covers GLP, 4chan, and any subreddit nobody claimed."
        actions={<Button onClick={startNew}>Add brand</Button>}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {brands.map((brand) => {
          const active = brand.id === selectedId;
          return (
            <button
              key={brand.id ?? brand.name}
              type="button"
              onClick={() => selectBrand(brand)}
              className={`rounded-lg border p-4 text-left transition ${
                active ? "border-primary bg-card shadow-soft" : "border-border bg-card hover:border-primary/40"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-foreground">{brand.name}</div>
                  <div className="text-sm text-muted-foreground">{brand.mention}</div>
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  {brand.is_active ? <Badge className="border-emerald-500/20 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">Default</Badge> : null}
                  {brand.is_enabled === false ? (
                    <Badge className="border-border bg-muted text-muted-foreground">Paused</Badge>
                  ) : (
                    <Badge className="border-sky-500/20 bg-sky-500/15 text-sky-600 dark:text-sky-400">Running</Badge>
                  )}
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {(brand.subreddits || []).length
                  ? `${brand.subreddits.length} subreddit${brand.subreddits.length === 1 ? "" : "s"}`
                  : brand.is_active
                    ? "Owns leftover subreddits"
                    : "No subreddits yet"}
              </p>
            </button>
          );
        })}
        {selectedId === "new" ? (
          <div className="rounded-lg border border-dashed border-primary bg-card p-4">
            <div className="font-medium text-foreground">New brand</div>
            <p className="mt-1 text-sm text-muted-foreground">Fill in the product on the right, then save.</p>
          </div>
        ) : null}
      </div>

      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-foreground">
            {selectedId === "new" ? "New brand" : selected?.name || "Brand"}
          </h3>
          <div className="flex flex-wrap gap-2">
            {selectedId !== "new" && selected && !selected.is_active ? (
              <Button type="button" variant="outline" onClick={setDefault} disabled={saving}>
                Make default
              </Button>
            ) : null}
            {selectedId !== "new" && selected && !selected.is_active ? (
              <Button type="button" variant="destructive" onClick={remove} disabled={saving}>
                Delete
              </Button>
            ) : null}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-foreground">Display name</span>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-foreground">Mention in replies</span>
            <Input value={form.mention} onChange={(e) => setForm({ ...form, mention: e.target.value })} />
          </label>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">One-liner</span>
          <Input
            value={form.one_liner}
            onChange={(e) => setForm({ ...form, one_liner: e.target.value })}
            placeholder="what this product does, in one short phrase"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Subreddits this brand owns (one per line)</span>
          <Textarea
            rows={4}
            value={form.subreddits}
            onChange={(e) => setForm({ ...form, subreddits: e.target.value })}
            placeholder="farming&#10;homestead&#10;MachineLearning"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Exclusive. A subreddit can belong to only one brand. Leave empty on the default brand to keep leftover communities.
          </span>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Aliases (one per line)</span>
          <Textarea rows={3} value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Topics to reply on</span>
          <Textarea
            rows={4}
            value={form.topics}
            onChange={(e) => setForm({ ...form, topics: e.target.value })}
            placeholder="AI, LLMs, farming, checkout…"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Promo ratio (0–1, blank = default)</span>
          <Input
            value={form.promo_ratio}
            onChange={(e) => setForm({ ...form, promo_ratio: e.target.value })}
            placeholder="0.10"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Example mentions</span>
          <Textarea
            rows={3}
            value={form.example_mentions}
            onChange={(e) => setForm({ ...form, example_mentions: e.target.value })}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-foreground">Banned salesy phrases</span>
          <Textarea
            rows={3}
            value={form.salesy_phrases}
            onChange={(e) => setForm({ ...form, salesy_phrases: e.target.value })}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_enabled}
            onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })}
          />
          Brand enabled — scrape its subs, but only draft replies while this is on
        </label>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {notice ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{notice}</p> : null}
        <Button onClick={save} disabled={saving}>
          {saving ? "Saving…" : selectedId === "new" ? "Create brand" : "Save brand"}
        </Button>
      </Card>
    </div>
  );
}
