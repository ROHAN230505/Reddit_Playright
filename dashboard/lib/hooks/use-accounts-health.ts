"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function useAccountsHealth(live: boolean) {
  return useQuery({
    queryKey: queryKeys.accountsHealth(live),
    queryFn: () => api.accountsHealth(live),
    refetchInterval: live ? 15_000 : false,
    placeholderData: (previous) => previous,
  });
}
