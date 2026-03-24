import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const nextConfig = (phase: string): NextConfig => ({
  distDir:
    phase === PHASE_DEVELOPMENT_SERVER
      ? ".forge-console-build-dev"
      : ".forge-console-build",
});

export default nextConfig;
