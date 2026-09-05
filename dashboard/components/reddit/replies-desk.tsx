"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";

const QueueBoard = dynamic(
  () => import("@/components/reddit/queue-board").then((mod) => mod.QueueBoard),
  { loading: () => <Skeleton className="mt-2 h-64 rounded-xl" /> },
);
const RealtimeBoard = dynamic(
  () => import("@/components/reddit/realtime-board").then((mod) => mod.RealtimeBoard),
  { loading: () => <Skeleton className="mt-2 h-40 rounded-xl" /> },
);

export function RepliesDesk() {
  const router = useRouter();
  const tab = useSearchParams().get("tab") === "realtime" ? "realtime" : "queue";
  const [queueVisited, setQueueVisited] = useState(tab === "queue");

  useEffect(() => {
    if (tab === "queue") setQueueVisited(true);
  }, [tab]);

  return (
    <Tabs
      value={tab}
      onValueChange={(value) => router.replace(`/replies?tab=${value}`)}
    >
      <TabsList>
        <TabsTrigger value="queue">Queue</TabsTrigger>
        <TabsTrigger value="realtime">Realtime</TabsTrigger>
      </TabsList>
      {queueVisited ? (
        <div hidden={tab !== "queue"} className="mt-2">
          <QueueBoard active={tab === "queue"} />
        </div>
      ) : null}
      {tab === "realtime" ? (
        <div className="mt-2">
          <RealtimeBoard />
        </div>
      ) : null}
    </Tabs>
  );
}
