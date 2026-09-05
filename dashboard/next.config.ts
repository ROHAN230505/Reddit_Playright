import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lucide-react", "motion", "cmdk"],
  },
};

export default nextConfig;
