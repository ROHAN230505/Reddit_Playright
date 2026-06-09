import * as React from "react";

type IconProps = React.SVGProps<SVGSVGElement>;

const common = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

// Reddit — comments / threads
export function MessageIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

// Reddit — Snoo-style brand mark
export function RedditIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path
        d="M17.9 10.2c.9.1 1.6.8 1.6 1.8 0 .6-.3 1.1-.7 1.4.1.4.2.8.2 1.2 0 3-3.1 5.4-7 5.4s-7-2.4-7-5.4c0-.4.1-.8.2-1.2-.4-.3-.7-.8-.7-1.4 0-1 .7-1.7 1.6-1.8 1.2-1.3 3.1-2.1 5.2-2.2l1-4.5 3.5.8c.3-.6.9-1 1.6-1a1.7 1.7 0 1 1-.4 3.3 1.7 1.7 0 0 1-1.1-1l-2.6-.6-.7 3.1c2.2.1 4.1.9 5.3 2.2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="9.4" cy="13.9" r="1" fill="currentColor" />
      <circle cx="14.6" cy="13.9" r="1" fill="currentColor" />
      <path
        d="M9.5 16.7c.9.6 2.3.8 3.5.6.6-.1 1.1-.3 1.5-.6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Godlike — power / energy
export function ZapIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

// GodlikeProductions — compact GLP-style wordmark
export function GodlikeIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <circle cx="12" cy="12" r="9.2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M16.8 8.3a5.7 5.7 0 1 0 0 7.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M9.4 12h4.2v4.1"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15.7 15.7h2.2c1.1 0 2-.9 2-2s-.9-2-2-2h-1.2V8.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// 4chan — boards grid
export function GridIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <rect width="7" height="7" x="3" y="3" rx="1.5" />
      <rect width="7" height="7" x="14" y="3" rx="1.5" />
      <rect width="7" height="7" x="14" y="14" rx="1.5" />
      <rect width="7" height="7" x="3" y="14" rx="1.5" />
    </svg>
  );
}

// 4chan — clover-style board mark
export function FourChanIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" {...props}>
      <path
        d="M11.2 11.1C8.5 10.5 6.6 8.9 6.6 6.8c0-1.4 1-2.4 2.4-2.4 2.1 0 3.2 2.2 3.5 5.7"
        fill="currentColor"
        opacity=".16"
      />
      <path
        d="M12.8 11.1c2.7-.6 4.6-2.2 4.6-4.3 0-1.4-1-2.4-2.4-2.4-2.1 0-3.2 2.2-3.5 5.7"
        fill="currentColor"
        opacity=".16"
      />
      <path
        d="M11.2 12.9c-2.7.6-4.6 2.2-4.6 4.3 0 1.4 1 2.4 2.4 2.4 2.1 0 3.2-2.2 3.5-5.7"
        fill="currentColor"
        opacity=".16"
      />
      <path
        d="M12.8 12.9c2.7.6 4.6 2.2 4.6 4.3 0 1.4-1 2.4-2.4 2.4-2.1 0-3.2-2.2-3.5-5.7"
        fill="currentColor"
        opacity=".16"
      />
      <path
        d="M12 12c-3.5-.1-5.4-2-5.4-4.2 0-1.4 1-2.4 2.4-2.4 2.2 0 3.5 2.5 3.5 6.6m-.5 0c3.5-.1 5.4-2 5.4-4.2 0-1.4-1-2.4-2.4-2.4-2.2 0-3.5 2.5-3.5 6.6m.5 0c-3.5.1-5.4 2-5.4 4.2 0 1.4 1 2.4 2.4 2.4 2.2 0 3.5-2.5 3.5-6.6m-.5 0c3.5.1 5.4 2 5.4 4.2 0 1.4-1 2.4-2.4 2.4-2.2 0-3.5-2.5-3.5-6.6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Instagram — DMs & comments triage
export function InstagramIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <rect width="20" height="20" x="2" y="2" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <line x1="17.5" x2="17.5" y1="6.5" y2="6.5" />
    </svg>
  );
}

// Brand mark — layered platforms
export function LayersIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m12 2 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </svg>
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}

export function LogOutIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" x2="9" y1="12" y2="12" />
    </svg>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <line x1="4" x2="20" y1="6" y2="6" />
      <line x1="4" x2="20" y1="12" y2="12" />
      <line x1="4" x2="20" y1="18" y2="18" />
    </svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <line x1="5" x2="19" y1="12" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m3 10 9-7 9 7" />
      <path d="M5 10v10h14V10" />
      <path d="M9 20v-6h6v6" />
    </svg>
  );
}

export function ActivityIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M3 12h4l3-8 4 16 3-8h4" />
    </svg>
  );
}

export function UsersIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    </svg>
  );
}

export function ListIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <line x1="8" x2="21" y1="6" y2="6" />
      <line x1="8" x2="21" y1="12" y2="12" />
      <line x1="8" x2="21" y1="18" y2="18" />
      <line x1="3" x2="3.01" y1="6" y2="6" />
      <line x1="3" x2="3.01" y1="12" y2="12" />
      <line x1="3" x2="3.01" y1="18" y2="18" />
    </svg>
  );
}

export function NewspaperIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M4 19.5A2.5 2.5 0 0 1 1.5 17V5A1.5 1.5 0 0 1 3 3.5h14A1.5 1.5 0 0 1 18.5 5v14.5" />
      <path d="M18.5 7H21a1.5 1.5 0 0 1 1.5 1.5V17a2.5 2.5 0 0 1-2.5 2.5H4" />
      <path d="M6 8h8" />
      <path d="M6 12h8" />
      <path d="M6 16h5" />
    </svg>
  );
}

export function ChartIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M3 3v18h18" />
      <rect x="7" y="12" width="3" height="5" rx="1" />
      <rect x="12" y="8" width="3" height="9" rx="1" />
      <rect x="17" y="5" width="3" height="12" rx="1" />
    </svg>
  );
}

export function FileTextIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8" />
      <path d="M8 17h5" />
      <path d="M8 9h2" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.1.32.28.6.53.82.26.22.58.34.92.34H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.84Z" />
    </svg>
  );
}
