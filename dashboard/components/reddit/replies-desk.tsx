"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RealtimeBoard } from "@/components/reddit/realtime-board";
import { QueueBoard } from "@/components/reddit/queue-board";

export function RepliesDesk() {
  const router = useRouter();
  const tab = useSearchParams().get("tab") === "realtime" ? "realtime" : "queue";
  return (
    <Tabs
      value={tab}
      onValueChange={(value) => router.replace(`/replies?tab=${value}`)}
    >
      <TabsList>
        <TabsTrigger value="queue">Queue</TabsTrigger>
        <TabsTrigger value="realtime">Realtime</TabsTrigger>
      </TabsList>
      <TabsContent value="queue"><QueueBoard /></TabsContent>
      <TabsContent value="realtime"><RealtimeBoard /></TabsContent>
    </Tabs>
  );
}
