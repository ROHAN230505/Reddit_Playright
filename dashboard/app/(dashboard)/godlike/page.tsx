import { Suspense } from "react";
import GodlikeSection from "@/components/sections/godlike-section";

export default function GodlikePage() {
  return (
    <Suspense>
      <GodlikeSection />
    </Suspense>
  );
}
