import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = {
  default: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
  secondary: "border border-border bg-card text-foreground shadow-sm hover:bg-muted",
  ghost: "text-foreground hover:bg-muted",
  danger: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
  accent: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
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

function buttonClassName(
  variant: keyof typeof buttonVariants = "default",
  size: keyof typeof buttonSizes = "default",
  className?: string,
) {
  return cn(
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring disabled:pointer-events-none disabled:opacity-50",
    buttonVariants[variant],
    buttonSizes[size],
    className,
  );
}

export function Button({ className, variant = "default", size = "default", ...props }: ButtonProps) {
  return <button className={buttonClassName(variant, size, className)} {...props} />;
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-border bg-card text-card-foreground shadow-soft", className)} {...props} />;
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-10 w-full rounded-md border border-border bg-transparent px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-1 focus:ring-ring",
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
        "min-h-28 w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-1 focus:ring-ring",
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
        "h-10 w-full rounded-md border border-border bg-transparent px-3 text-sm text-foreground outline-none focus:border-ring focus:ring-1 focus:ring-ring",
        props.className,
      )}
    />
  );
}

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function FieldLabel({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground", className)}
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
        <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
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
    neutral: "border-dashed border-border bg-muted/50 text-foreground",
    error: "border-destructive/30 bg-destructive/10 text-destructive",
    warning: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
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

export const tableHeadClassName = "bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground";
export const tableRowClassName = "border-t border-border hover:bg-muted/50";
export const tableCellClassName = "px-4 py-3 align-top";
