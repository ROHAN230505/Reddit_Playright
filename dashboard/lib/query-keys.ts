export const queryKeys = {
  accountsHealth: (live: boolean) => ["accounts-health", live] as const,
  replies: (status: string, extra: Record<string, unknown> = {}) => ["replies", status, extra] as const,
  repliesSummary: (status: string, platform?: string) => ["replies-summary", status, platform] as const,
  proxies: () => ["proxies"] as const,
  brands: () => ["brands"] as const,
  redditAutomation: (filters: Record<string, unknown>) => ["reddit-automation", filters] as const,
  dashboardSummary: () => ["dashboard-summary"] as const,
  workerQueue: (platform: string) => ["worker-queue", platform] as const,
};
