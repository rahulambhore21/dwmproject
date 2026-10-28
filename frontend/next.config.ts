import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // The browser only ever talks to this origin; /api/* is proxied to FastAPI.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  // e2e runs use their own build dir so they can run beside a developer's `npm run dev` (Next allows one dev server per dir).
  distDir: process.env.NEXT_DIST_DIR || undefined,
  poweredByHeader: false,
};

export default nextConfig;
