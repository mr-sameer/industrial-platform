/** @type {import('next').NextConfig} */
const isProduction = process.env.NODE_ENV === "production";

// Security headers — Module 2.5 Phase 12. Unlike the API (JSON-only,
// locked to default-src 'none' — see app.core.security_headers), the web
// app renders HTML/CSS/JS itself, so its CSP has to actually allow those.
// 'unsafe-inline' for style-src is needed for Next.js's inline critical
// CSS; there is currently no inline script usage, so script-src omits it.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), camera=(), microphone=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
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
