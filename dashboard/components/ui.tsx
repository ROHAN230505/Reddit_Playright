import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = {
  default: "bg-slate-900 text-white shadow-sm hover:bg-slate-800",
  secondary: "border border-border bg-white text-slate-800 shadow-sm hover:bg-slate-50",
  ghost: "text-slate-700 hover:bg-slate-100",
  danger: "bg-danger text-white shadow-sm hover:bg-red-800",
  accent: "bg-accent text-white shadow-sm hover:bg-teal-800",
};

const buttonSizes = {
  default: "h-10 px-4",
  sm: "h-8 px-3 text-xs",
  icon: "h-9 w-9 p-0",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof buttonVariants;
  size?: keyof typeof buttonSizes;
}

export function buttonClassName(
  variant: keyof typeof buttonVariants = "default",
  size: keyof typeof buttonSizes = "default",
  className?: string,
) {
  return cn(
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:pointer-events-none disabled:opacity-50",
    buttonVariants[variant],
    buttonSizes[size],
    className,
  );
}

export function Button({ className, variant = "default", size = "default", ...props }: ButtonProps) {
  return <button className={buttonClassName(variant, size, className)} {...props} />;
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-border bg-panel shadow-soft", className)} {...props} />;
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-10 w-full rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/15",
        props.className,
      )}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-28 w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/15",
        props.className,
      )}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-10 w-full rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/15",
        props.className,
      )}
    />
  );
}

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-slate-200", className)} />;
}

export function FieldLabel({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1 block text-xs font-semibold uppercase tracking-wide text-muted", className)}
      {...props}
    />
  );
}

export function SectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div className="min-w-0">
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StateMessage({
  title,
  description,
  tone = "neutral",
  compact = false,
  className,
}: {
  title: string;
  description?: string;
  tone?: "neutral" | "error" | "warning" | "success";
  compact?: boolean;
  className?: string;
}) {
  const tones = {
    neutral: "border-dashed border-border bg-slate-50 text-slate-700",
    error: "border-red-200 bg-red-50 text-danger",
    warning: "border-amber-200 bg-amber-50 text-warning",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  };
  return (
    <div className={cn("rounded-md border text-center", tones[tone], compact ? "p-4" : "p-6", className)}>
      <div className="text-sm font-medium">{title}</div>
      {description && <div className="mt-1 text-sm opacity-80">{description}</div>}
    </div>
  );
}

export function TableShell({
  children,
  minWidth = 900,
  className,
}: {
  children: React.ReactNode;
  minWidth?: number;
  className?: string;
}) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full text-left text-sm" style={{ minWidth }}>
        {children}
      </table>
    </div>
  );
}

export const tableHeadClassName = "bg-slate-50 text-xs uppercase tracking-wide text-muted";
export const tableRowClassName = "border-t border-border hover:bg-slate-50/70";
export const tableCellClassName = "px-4 py-3 align-top";
