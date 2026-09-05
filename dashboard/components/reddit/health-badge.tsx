import { Badge } from "@/components/ui/badge";
import type { RedditAccountItem } from "@/lib/api";
import { displayStatus, isBanned, sessionCaption } from "@/lib/health";
import { cn } from "@/lib/utils";

function badgeLabel(account: RedditAccountItem) {
  if (isBanned(account)) return "BANNED";
  if (account.reddit_health === "HEALTHY") return "HEALTHY";
  return account.reddit_health ?? displayStatus(account);
}

function badgeVariant(account: RedditAccountItem) {
  if (isBanned(account)) return "destructive" as const;
  if (account.reddit_health === "HEALTHY") return "outline" as const;
  return "secondary" as const;
}

export function HealthBadge({
  account,
  className,
}: {
  account: RedditAccountItem;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start", className)}>
      <Badge variant={badgeVariant(account)}>{badgeLabel(account)}</Badge>
      <p className="mt-0.5 text-xs text-muted-foreground">{sessionCaption(account)}</p>
    </div>
  );
}
