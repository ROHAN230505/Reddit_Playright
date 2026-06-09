import { Suspense } from "react";
import AnalyticsDashboardSection from "@/components/sections/analytics-dashboard-section";

export default function AnalyticsPage() {
  return (
    <Suspense>
      <AnalyticsDashboardSection />
    </Suspense>
  );
}
