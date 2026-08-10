import type { NextConfig } from "next";

const internalApiOrigin = (process.env.INTERNAL_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiOrigin}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${internalApiOrigin}/health`,
      },
      {
        source: "/ready",
        destination: `${internalApiOrigin}/ready`,
      },
    ];
  },
};

export default nextConfig;
