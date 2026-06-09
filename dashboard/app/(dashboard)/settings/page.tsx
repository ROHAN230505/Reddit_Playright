import { Suspense } from "react";
import SettingsSection from "@/components/sections/settings-section";

export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsSection />
    </Suspense>
  );
}
