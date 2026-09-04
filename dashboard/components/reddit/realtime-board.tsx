"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { HealthBadge } from "@/components/reddit/health-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RedditAccountItem } from "@/lib/api";
import { isBanned, realtimeVisible } from "@/lib/health";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";
import { queryKeys } from "@/lib/query-keys";

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 4 }, (_, index) => (
        <Skeleton key={index} className="h-40 rounded-xl" />
      ))}
    </div>
  );
}

function ErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Could not load account health</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-2">
        <span>The live health fetch failed. Previous data stays if it is available.</span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}

function EmptyAccounts() {
  return (
    <Card className="p-8 text-center">
      <p className="text-sm font-medium">No Reddit accounts</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Add a Reddit account in settings to see live health here.
      </p>
      <Button asChild className="mt-4">
        <Link href="/settings?tab=accounts">Go to accounts</Link>
      </Button>
    </Card>
  );
}

function AccountCard({ account }: { account: RedditAccountItem }) {
  const queryClient = useQueryClient();
  const reverify = useMutation({
    mutationFn: () => api.reverifyAccount(account.id),
    onSuccess: () => {
      toast.success(`Reverify started for ${account.username}`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountsHealth(true) });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Reverify failed");
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 p-4 pb-3">
        <div className="min-w-0 space-y-2">
          <CardTitle className="truncate font-mono text-sm font-medium">
            {account.username}
          </CardTitle>
          <HealthBadge account={account} />
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={reverify.isPending}
          onClick={() => reverify.mutate()}
        >
          <RefreshCw className={reverify.isPending ? "animate-spin" : undefined} />
          Reverify
        </Button>
      </CardHeader>
      <CardContent className="space-y-2 p-4 pt-0">
        <p className="text-sm text-muted-foreground">{account.proxy_label ?? "No proxy"}</p>
        {isBanned(account) && account.reddit_session_alive ? (
          <p className="text-sm text-destructive">
            Public profile is banned. A live session cannot post.
          </p>
        ) : null}
        {account.last_error ? (
          <p className="whitespace-pre-wrap break-words text-sm text-destructive">
            {account.last_error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function RealtimeBoard() {
  const { data, isPending, isError, refetch } = useAccountsHealth(true);
  const accounts = (data?.accounts ?? []).filter(realtimeVisible);

  if (isPending && !data) {
    return <LoadingGrid />;
  }

  if (isError && !data) {
    return <ErrorBanner onRetry={() => void refetch()} />;
  }

  return (
    <div className="space-y-4">
      {isError ? <ErrorBanner onRetry={() => void refetch()} /> : null}
      {accounts.length === 0 ? (
        <EmptyAccounts />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {accounts.map((account) => (
            <AccountCard key={account.id} account={account} />
          ))}
        </div>
      )}
    </div>
  );
}
