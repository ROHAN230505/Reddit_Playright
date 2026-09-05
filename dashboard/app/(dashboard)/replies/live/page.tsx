import { redirect } from "next/navigation";

// Live data — never cache. Without this, Next.js statically prerenders the
// HTML shell and serves it with x-nextjs-cache:HIT, which can pin browsers
// to a stale chunk reference even after rebuilds.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function RepliesLivePage() {
  redirect("/replies?tab=realtime");
}
