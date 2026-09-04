import { Suspense } from "react";
import { redirect } from "next/navigation";
import SettingsSection from "@/components/sections/settings-section";

type SettingsPageProps = {
  searchParams: Promise<{ tab?: string | string[] }>;
};

export default async function SettingsPage({ searchParams }: SettingsPageProps) {
  const params = await searchParams;
  const tab = Array.isArray(params.tab) ? params.tab[0] : params.tab;
  if (tab === "queue") {
    redirect("/replies?tab=queue");
  }

  return (
    <Suspense>
      <SettingsSection />
    </Suspense>
  );
}
