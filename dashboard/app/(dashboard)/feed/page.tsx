import { redirect } from "next/navigation";

export default function FeedPage() {
  redirect("/analytics?tab=feed");
}
