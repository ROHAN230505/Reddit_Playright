import { Suspense } from "react";
import ChanSection from "@/components/sections/chan-section";

export default function ChanPage() {
  return (
    <Suspense>
      <ChanSection />
    </Suspense>
  );
}
