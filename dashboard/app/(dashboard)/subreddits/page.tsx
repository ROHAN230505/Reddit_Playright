import { redirect } from "next/navigation";

export default function SubredditsPage() {
  redirect("/settings?tab=subreddits");
}
