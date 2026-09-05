/**
 * TanStack Query refetch interval.
 *
 * Always return the number so the timer stays armed while the tab is hidden.
 * `refetchIntervalInBackground: false` (QueryClient default) skips the fetch
 * itself. Returning `false` from this helper would *clear* the timer, and
 * Query would not start it again until something else re-rendered the observer.
 */
export function visibleRefetchInterval(ms: number): number {
  return ms;
}
