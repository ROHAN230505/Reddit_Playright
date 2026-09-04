import { Suspense } from "react";
import { RepliesDesk } from "@/components/reddit/replies-desk";

export default function RepliesPage() {
  return (
    <Suspense>
      <RepliesDesk />
    </Suspense>
  );
}
