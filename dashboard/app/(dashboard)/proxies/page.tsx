import { redirect } from "next/navigation";

export default function ProxiesPage() {
  redirect("/settings?tab=proxies");
}
