/** @type {import('next').NextConfig} */
const isProduction = process.env.NODE_ENV === "production";

// Security headers — Module 2.5 Phase 12, Content-Security-Policy moved
// to middleware.ts (see docs/adr/0031-csp-blocked-hydration.md).
// CSP needs a fresh per-request nonce for Next.js's own inline
// hydration scripts to work at all, which a static config value here
// can't provide — middleware.ts sets it dynamically instead. Do NOT
// add a Content-Security-Policy entry back here: browsers enforce
// multiple CSP headers by intersection, so a static nonce-less policy
// here would silently re-block every script even with middleware's
// correct one also present.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), camera=(), microphone=()" },
  ...(isProduction
    ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
    : []),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // required for the lean multi-stage Docker image
  transpilePackages: ["@platform/shared-types", "@platform/ui"],
  experimental: {
    instrumentationHook: true,
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
