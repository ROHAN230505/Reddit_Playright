"use client";

import type { ComponentType, SVGProps } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { BarChart3, LogOut, MessageCircle, Settings } from "lucide-react";
import { PLATFORMS } from "@/components/platforms";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

type RailItem = {
  href: string;
  label: string;
  Icon: Icon;
  muted?: boolean;
  external?: boolean;
};

const PRIMARY_ITEMS: RailItem[] = [
  { href: "/replies", label: "Reddit", Icon: MessageCircle },
  { href: "/analytics", label: "Analytics", Icon: BarChart3 },
  { href: "/settings", label: "Settings", Icon: Settings },
];

const OTHER_PLATFORM_ITEMS: RailItem[] = PLATFORMS.filter((item) => item.platform !== "reddit").map(
  (item) => ({
    href: item.href,
    label: item.label,
    Icon: item.Icon,
    muted: true,
    external: item.external,
  }),
);

async function logout() {
  await fetch("/api/login", { method: "DELETE" });
  window.location.assign("/login");
}

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function RailLink({
  item,
  active,
  layoutId,
  onNavigate,
}: {
  item: RailItem;
  active: boolean;
  layoutId?: string;
  onNavigate?: () => void;
}) {
  const className = cn(
    "relative flex h-10 w-full items-center justify-center text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
    active && "bg-secondary text-foreground",
    item.muted && !active && "opacity-60",
  );

  const inner = (
    <>
      {active &&
        (layoutId ? (
          <motion.span
            layoutId={layoutId}
            className="absolute inset-y-0 left-0 w-0.5 bg-primary"
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
          />
        ) : (
          <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />
        ))}
      <item.Icon className="h-4 w-4" />
    </>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {item.external ? (
          <a
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={item.label}
            className={className}
            onClick={onNavigate}
          >
            {inner}
          </a>
        ) : (
          <Link href={item.href} aria-label={item.label} className={className} onClick={onNavigate}>
            {inner}
          </Link>
        )}
      </TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

export function IconRail({
  onNavigate,
  layoutId,
}: {
  onNavigate?: () => void;
  layoutId?: string;
}) {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-14 flex-col border-r bg-background">
      <nav className="flex min-h-0 w-full flex-1 flex-col items-center gap-1 overflow-y-auto py-3">
        {PRIMARY_ITEMS.map((item) => (
          <RailLink
            key={item.href}
            item={item}
            active={isActive(pathname, item.href)}
            layoutId={layoutId}
            onNavigate={onNavigate}
          />
        ))}
        {OTHER_PLATFORM_ITEMS.length > 0 && (
          <>
            <Separator className="mx-auto my-2 w-8" />
            {OTHER_PLATFORM_ITEMS.map((item) => (
              <RailLink
                key={item.href}
                item={item}
                active={isActive(pathname, item.href)}
                layoutId={layoutId}
                onNavigate={onNavigate}
              />
            ))}
          </>
        )}
      </nav>
      <div className="mt-auto flex flex-col items-center gap-1 border-t py-3">
        <ThemeToggle />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="icon" aria-label="Log out" onClick={logout}>
              <LogOut />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Logout</TooltipContent>
        </Tooltip>
      </div>
    </aside>
  );
}
