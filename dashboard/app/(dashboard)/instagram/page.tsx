import { Suspense } from "react";
import InstagramSection from "@/components/sections/instagram-section";

export default function InstagramPage() {
  return (
    <Suspense>
      <InstagramSection />
    </Suspense>
  );
}
