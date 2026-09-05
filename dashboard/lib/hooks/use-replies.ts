"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";

export function usePendingReplies(brandId?: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.replies("PENDING", { brandId, platform: "reddit" }),
    queryFn: () =>
      api.replies("PENDING", 500, undefined, "newest", 40, "reddit", brandId),
    staleTime: 10_000,
    refetchInterval: enabled ? visibleRefetchInterval(15_000) : false,
    refetchIntervalInBackground: false,
    enabled,
    placeholderData: (previous) => previous,
  });
}

export function useUpdateReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      reply_text,
    }: {
      id: number;
      status?: string;
      reply_text?: string;
    }) => api.updateReply(id, { status, reply_text }),
    onSuccess: () => {
      toast.success("Reply updated");
      void qc.invalidateQueries({ queryKey: ["replies"] });
      void qc.invalidateQueries({ queryKey: ["accounts-health"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
