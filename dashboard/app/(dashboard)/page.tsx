"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Platform, type ReplyItem } from "@/lib/api";
import { Card, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import { PLATFORMS } from "@/components/platforms";
import { ArrowRightIcon } from "@/components/icons";
import { RecentlyPostedPanel } from "@/components/recently-posted";

const LIMIT = 200;
const OVERVIEW_PLATFORMS = PLATFORMS.filter((item) => item.platform !== "instagram");

export default function HomePage() {
  const [pending, setPending] = useState<Partial<Record<Platform, number | null>>>({
    reddit: null,
    glp: null,
    chan: null,
  });
  const [posted, setPosted] = useState<ReplyItem[]>([]);

  useEffect(() => {
    let active = true;
    const load = () => {
      Promise.all(
        OVERVIEW_PLATFORMS.map((card) =>
          api
            .replies("PENDING", LIMIT, undefined, "upvotes", 0, card.platform)
            .then((rows) => [card.platform, rows.length] as const)
            .catch(() => [card.platform, null] as const),
        ),
      ).then((entries) => {
        if (active) setPending((prev) => ({ ...prev, ...Object.fromEntries(entries) }));
      });
      // Global recently-posted feed — no platform filter (all platforms).
      api
        .replies("POSTED", 50, undefined, "newest")
        .then((rows) => {
          if (active) setPosted(rows);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORMS.map((card) => {
        const count = pending[card.platform];
        const display = card.platform === "instagram" ? "Open" : count == null ? null : count >= LIMIT ? `${LIMIT}+` : String(count);
        return (
          <Link key={card.href} href={card.href} className="group block">
            <Card className="flex h-full flex-col justify-between gap-6 p-5 transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-slate-300 group-hover:shadow-lift">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "flex h-11 w-11 items-center justify-center rounded-xl ring-1 ring-inset",
                      card.chipBg,
                      card.chipText,
                      card.chipRing,
                    )}
                  >
                    <card.Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <div className="text-base font-semibold tracking-tight text-slate-900">{card.label}</div>
                    <div className="text-xs text-muted">{card.blurb}</div>
                  </div>
                </div>
                <ArrowRightIcon className="h-5 w-5 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
              </div>
              <div>
                {display === null ? (
                  <Skeleton className="h-10 w-20" />
                ) : card.platform === "instagram" ? (
                  <div className="text-3xl font-semibold tracking-tight text-slate-900">{display}</div>
                ) : (
                  <div className="text-4xl font-semibold tracking-tight text-slate-900">{display}</div>
                )}
                <div className="mt-1 text-xs font-medium uppercase tracking-wide text-muted">
                  {card.platform === "instagram" ? "Native dashboard" : "Pending replies"}
                </div>
              </div>
            </Card>
          </Link>
        );
        })}
      </div>

      <RecentlyPostedPanel posted={posted} subtitle="All platforms · newest first" />
    </div>
  );
}
