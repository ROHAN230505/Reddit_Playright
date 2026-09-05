import type { ComponentType, SVGProps } from "react";
import type { Platform } from "@/lib/api";
import { FourChanIcon, GodlikeIcon, InstagramIcon, RedditIcon } from "@/components/icons";

export type PlatformDef = {
  href: string;
  label: string;
  blurb: string;
  platform: Platform;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  chipBg: string;
  chipText: string;
  chipRing: string;
  // When true, `href` is an external URL (the instagram service's own UI) and the
  // nav renders an <a target="_blank"> instead of an in-app Next <Link>.
  external?: boolean;
};

const ALL_PLATFORMS: PlatformDef[] = [
  {
    href: "/replies",
    label: "Reddit",
    blurb: "Reddit threads",
    platform: "reddit",
    Icon: RedditIcon,
    chipBg: "bg-orange-500/10",
    chipText: "text-orange-500",
    chipRing: "ring-orange-500/20",
  },
  {
    href: "/godlike",
    label: "Godlike",
    blurb: "GodlikeProductions",
    platform: "glp",
    Icon: GodlikeIcon,
    chipBg: "bg-violet-500/10",
    chipText: "text-violet-400",
    chipRing: "ring-violet-500/20",
  },
  {
    href: "/4chan",
    label: "4chan",
    blurb: "Image boards",
    platform: "chan",
    Icon: FourChanIcon,
    chipBg: "bg-emerald-500/10",
    chipText: "text-emerald-400",
    chipRing: "ring-emerald-500/20",
  },
  {
    // Native in-app section. It reads the instagram (doomscroller) service's
    // JSON API through the dashboard's server-side proxy (/api/instagram/*), so
    // it renders inside the dashboard shell behind the same login. The full
    // operator UI (login, advanced controls) is still linked from the section.
    href: "/instagram",
    label: "Instagram",
    blurb: "DMs & comments triage",
    platform: "instagram",
    Icon: InstagramIcon,
    chipBg: "bg-pink-500/10",
    chipText: "text-pink-400",
    chipRing: "ring-pink-500/20",
  },
];

const ENABLED_PLATFORMS = (process.env.NEXT_PUBLIC_ENABLED_PLATFORMS || "reddit")
  .split(",")
  .map((item) => item.trim().toLowerCase())
  .filter(Boolean);

export const PLATFORMS: PlatformDef[] =
  ENABLED_PLATFORMS.includes("all")
    ? ALL_PLATFORMS
    : ALL_PLATFORMS.filter((item) => ENABLED_PLATFORMS.includes(item.platform));
