"use client";

import { useState, Suspense } from "react";
import { NoticeProvider } from "@/lib/notice-context";
import { IconRail } from "@/components/shell/icon-rail";
import { TopBar } from "@/components/shell/top-bar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

function DashboardShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      <div className="hidden lg:flex">
        <IconRail layoutId="rail-active" />
      </div>
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent
          side="left"
          className="w-14 p-0 sm:max-w-[3.5rem] [&>button]:hidden"
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <IconRail onNavigate={() => setMobileNavOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <Suspense fallback={<div className="h-14 border-b bg-background" />}>
          <TopBar onMenuClick={() => setMobileNavOpen(true)} />
        </Suspense>
        <div className="min-w-0 flex-1 p-4 md:p-6">{children}</div>
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <NoticeProvider>
      <DashboardShell>{children}</DashboardShell>
    </NoticeProvider>
  );
}
