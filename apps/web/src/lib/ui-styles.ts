import type { CSSProperties } from "react";

/**
 * Minimal shared inline-style constants for Module 3A's company pages —
 * matches the plain-inline-style convention already established by
 * Module 2's auth pages (src/app/(auth)/login/page.tsx etc.) rather than
 * introducing a CSS framework for this module. Centralized here so the
 * ~6 new pages don't each redefine the same container/card/button
 * styles (docs/standards/coding-standards.md: "no duplicated logic").
 * Responsive behavior comes from CSS Grid `auto-fit`/`minmax` and
 * `max-width` + fluid containers rather than breakpoint-specific rules,
 * which is sufficient for this module's layouts.
 */

export const page: CSSProperties = {
  fontFamily: "ui-sans-serif, system-ui, sans-serif",
  padding: "clamp(1.25rem, 4vw, 3rem)",
  maxWidth: 960,
  margin: "0 auto",
};

export const card: CSSProperties = {
  border: "1px solid #e2e2e2",
  borderRadius: 8,
  padding: "1.25rem",
  background: "#fff",
};

export const cardGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
  gap: "1rem",
};

export const formField: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.35rem",
};

export const input: CSSProperties = {
  padding: "0.5rem 0.65rem",
  border: "1px solid #ccc",
  borderRadius: 6,
  fontSize: "0.95rem",
};

export const button: CSSProperties = {
  padding: "0.55rem 1rem",
  borderRadius: 6,
  border: "1px solid #1a3c34",
  background: "#1a3c34",
  color: "#fff",
  cursor: "pointer",
  fontSize: "0.9rem",
};

export const buttonSecondary: CSSProperties = {
  ...button,
  background: "#fff",
  color: "#1a3c34",
};

export const buttonDanger: CSSProperties = {
  ...button,
  background: "#cf222e",
  border: "1px solid #cf222e",
};

export const errorText: CSSProperties = { color: "#cf222e", fontSize: "0.9rem" };

export const mutedText: CSSProperties = { color: "#666", fontSize: "0.85rem" };

export const badge: CSSProperties = {
  display: "inline-block",
  padding: "0.15rem 0.55rem",
  borderRadius: 999,
  fontSize: "0.75rem",
  fontWeight: 600,
};

export function badgeForVerification(status: "unverified" | "verified"): CSSProperties {
  return {
    ...badge,
    background: status === "verified" ? "#e6f4ea" : "#f6f7f8",
    color: status === "verified" ? "#1a7f37" : "#666",
  };
}

// Mirrors the Observed/Verified provenance badges already established in
// components/consult/RecommendationCard.tsx — same rule, same two colors,
// just as inline styles instead of Tailwind classes to match this
// module's convention. A value is "Verified" only when the backend
// itself reports status="verified"; everything else observed is
// "Observed", never upgraded.
export const badgeObserved: CSSProperties = { ...badge, background: "#eef2ff", color: "#3538cd" };
export const badgeVerified: CSSProperties = { ...badge, background: "#e6f4ea", color: "#1a7f37" };

export const evidenceCard: CSSProperties = {
  ...card,
  background: "#fafafa",
};

export const link: CSSProperties = { color: "#1a3c34", fontWeight: 500 };
