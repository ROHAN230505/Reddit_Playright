"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";

export function useAccountsHealth(live: boolean) {
  return useQuery({
    queryKey: queryKeys.accountsHealth(live),
    queryFn: () => api.accountsHealth(live),
    // Live hits Reddit public profiles. Stored is a cheap DB read.
    staleTime: live ? 20_000 : 15_000,
    refetchInterval: visibleRefetchInterval(live ? 20_000 : 15_000),
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });
}
