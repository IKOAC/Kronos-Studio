import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  // The editorial terminal has its own status indicators.
  devIndicators: false,
};

export default nextConfig;
