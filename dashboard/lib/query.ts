/** Pause TanStack Query polling while the browser tab is in the background. */
export function visibleRefetchInterval(ms: number) {
  return () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      return false;
    }
    return ms;
  };
}
