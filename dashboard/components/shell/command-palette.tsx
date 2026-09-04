"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { api } from "@/lib/api";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";

const GO_TO = [
  { label: "Queue", href: "/replies?tab=queue" },
  { label: "Realtime", href: "/replies?tab=realtime" },
  { label: "Analytics", href: "/analytics" },
  { label: "Accounts", href: "/settings?tab=accounts" },
  { label: "Proxies", href: "/settings?tab=proxies" },
  { label: "Subreddits", href: "/settings?tab=subreddits" },
  { label: "Brand", href: "/settings?tab=brand" },
] as const;

export function CommandPalette() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);

  const openPalette = useCallback(() => {
    setMounted(true);
    setOpen(true);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
      }
    }
    function onCommand() {
      openPalette();
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("replyops:command", onCommand);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("replyops:command", onCommand);
    };
  }, [openPalette]);

  if (!mounted) return null;

  return <CommandPaletteDialog open={open} onOpenChange={setOpen} />;
}

function CommandPaletteDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { data } = useAccountsHealth(false);
  const accounts = (data?.accounts ?? []).filter(
    (account) => (account.platform || "reddit") === "reddit",
  );

  function runCommand(command: () => void) {
    onOpenChange(false);
    command();
  }

  function goTo(href: string) {
    runCommand(() => router.push(href));
  }

  async function scrapeNow() {
    try {
      await api.scrapeAll(15);
      toast.success("Scrape queued for tracked subs");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Scrape failed");
    }
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Jump to a page, account, or action…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Go to">
          {GO_TO.map((item) => (
            <CommandItem
              key={item.href}
              value={`go ${item.label}`}
              onSelect={() => goTo(item.href)}
            >
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        {accounts.length > 0 ? (
          <CommandGroup heading="Accounts">
            {accounts.map((account) => (
              <CommandItem
                key={account.id}
                value={`account ${account.username}`}
                onSelect={() => goTo("/settings?tab=accounts")}
              >
                <span className="font-mono">{account.username}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}
        <CommandGroup heading="Actions">
          <CommandItem value="scrape now" onSelect={() => runCommand(() => void scrapeNow())}>
            Scrape now
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
