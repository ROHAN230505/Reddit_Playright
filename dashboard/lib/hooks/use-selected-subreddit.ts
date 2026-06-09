"use client";

import { useRouter, useSearchParams } from "next/navigation";

export function useSelectedSubreddit(): [string, (next: string) => void] {
  const router = useRouter();
  const searchParams = useSearchParams();
  const value = searchParams.get("sub") ?? "";

  const setValue = (next: string) => {
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    if (next) params.set("sub", next);
    else params.delete("sub");
    router.replace(`?${params.toString()}`);
  };

  return [value, setValue];
}
