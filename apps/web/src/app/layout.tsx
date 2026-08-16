import type { Metadata } from "next";
import type { ReactNode } from "react";

import { env } from "@/config/env";
import { AuthProvider } from "@/contexts/AuthContext";

// Self-hosted font files via @fontsource — not next/font/google. This
// environment (and potentially some deployment targets) has no build-
// time network access to fonts.googleapis.com; @fontsource ships the
// actual font files inside the npm package, so there is zero external
// network dependency at build or runtime, in any environment. Space
// Grotesk weights are intentionally limited (500/600/700 — display use
// only, per the design plan's "restraint" principle); Inter and IBM
// Plex Mono load their normal text weights.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";

// Required for the nonce-based CSP in middleware.ts to actually work
// (see docs/adr/0031-csp-blocked-hydration.md). A statically-generated
// page's HTML — including Next.js's own inline hydration scripts — is
// fixed at build time; there is no per-request opportunity to embed a
// nonce that matches whatever middleware puts in that request's CSP
// header. Confirmed via real production-build browser testing: inline
// scripts stayed blocked on static pages (/login, /register) even
// after the middleware nonce fix, until this was added. Next.js's own
// CSP guide documents this as a requirement, not an incidental choice.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: env.appName,
  description: "ForgeX — AI-Powered Industrial Intelligence Platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
