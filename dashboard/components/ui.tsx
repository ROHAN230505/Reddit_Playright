import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = {
  default: "bg-slate-900 text-white hover:bg-slate-800",
  secondary: "border border-border bg-white text-slate-800 hover:bg-slate-50",
  ghost: "text-slate-700 hover:bg-slate-100",
  danger: "bg-danger text-white hover:bg-red-800",
  accent: "bg-accent text-white hover:bg-teal-800",
};

const buttonSizes = {
  default: "h-10 px-4",
  sm: "h-8 px-3 text-xs",
  icon: "h-9 w-9",
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
    "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:pointer-events-none disabled:opacity-50",
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
