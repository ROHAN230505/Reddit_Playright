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

export const PLATFORMS: PlatformDef[] = [
  {
    href: "/replies",
    label: "Reddit",
    blurb: "Reddit threads",
    platform: "reddit",
    Icon: RedditIcon,
    chipBg: "bg-orange-50",
    chipText: "text-orange-600",
    chipRing: "ring-orange-100",
  },
  {
    href: "/godlike",
    label: "Godlike",
    blurb: "GodlikeProductions",
    platform: "glp",
    Icon: GodlikeIcon,
    chipBg: "bg-violet-50",
    chipText: "text-violet-600",
    chipRing: "ring-violet-100",
  },
  {
    href: "/4chan",
    label: "4chan",
    blurb: "Image boards",
    platform: "chan",
    Icon: FourChanIcon,
    chipBg: "bg-emerald-50",
    chipText: "text-emerald-600",
    chipRing: "ring-emerald-100",
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
    chipBg: "bg-pink-50",
    chipText: "text-pink-600",
    chipRing: "ring-pink-100",
  },
];
