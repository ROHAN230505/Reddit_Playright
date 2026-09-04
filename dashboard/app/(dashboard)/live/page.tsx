import { redirect } from "next/navigation";

export default function LivePage() {
  redirect("/replies?tab=realtime");
}
