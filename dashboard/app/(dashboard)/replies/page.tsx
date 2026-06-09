import { Suspense } from "react";
import RepliesSection from "@/components/sections/replies-section";

export default function RepliesPage() {
  return (
    <Suspense>
      <RepliesSection />
    </Suspense>
  );
}
