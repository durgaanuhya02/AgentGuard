import type { NextConfig } from "next";

// The dashboard talks to the AgentGuard API through /api/* on the same origin, so the WorkOS
// session cookie set by the API works without any CORS setup.
// 127.0.0.1 rather than localhost: on Windows "localhost" tries IPv6 first and adds ~2 s per call.
const API_URL = process.env.AGENTGUARD_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
