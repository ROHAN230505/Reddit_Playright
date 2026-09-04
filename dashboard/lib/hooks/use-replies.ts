"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function usePendingReplies(brandId?: number) {
  return useQuery({
    queryKey: queryKeys.replies("PENDING", { brandId, platform: "reddit" }),
    queryFn: () =>
      api.replies("PENDING", 500, undefined, "newest", 40, "reddit", brandId),
    refetchInterval: 15_000,
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
      void qc.invalidateQueries({ queryKey: queryKeys.accountsHealth(true) });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
