import type { Config } from "tailwindcss";

/**
 * Design tokens — Frontend Integration Sprint, Phase 1. See
 * docs/architecture/design-system.md for the full rationale (palette
 * grounded in "industrial precision" via a blueprint-blue accent,
 * verification-level color progression, restrained display-font usage).
 *
 * Colors are expressed as CSS custom properties (set in globals.css) so
 * the same token name could support a future theme switch without
 * touching every component — not building that switch now (out of
 * scope), just not foreclosing it.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        "surface-hover": "var(--color-surface-hover)",
        sidebar: "var(--color-sidebar)",
        "sidebar-hover": "var(--color-sidebar-hover)",
        "sidebar-active": "var(--color-sidebar-active)",
        border: "var(--color-border)",
        "border-strong": "var(--color-border-strong)",
        "sidebar-border": "var(--color-sidebar-border)",
        ink: "var(--color-ink)",
        "ink-muted": "var(--color-ink-muted)",
        "ink-faint": "var(--color-ink-faint)",
        "ink-inverse": "var(--color-ink-inverse)",
        "ink-inverse-muted": "var(--color-ink-inverse-muted)",
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          subtle: "var(--color-accent-subtle)",
        },
        success: { DEFAULT: "var(--color-success)", subtle: "var(--color-success-subtle)" },
        warning: { DEFAULT: "var(--color-warning)", subtle: "var(--color-warning-subtle)" },
        danger: { DEFAULT: "var(--color-danger)", subtle: "var(--color-danger-subtle)" },
        // Verification-level progression — see docs/architecture/design-system.md.
        "level-unverified": "var(--color-level-unverified)",
        "level-email": "var(--color-level-email)",
        "level-business": "var(--color-level-business)",
        "level-factory": "var(--color-level-factory)",
        "level-premium": "var(--color-level-premium)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Inter", "ui-sans-serif", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "8px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      },
      boxShadow: {
        // Deliberately sparse — hairline borders do most of the work
        // (Stripe/Linear-style flatness); shadows reserved for floating
        // layers only.
        popover: "0 8px 24px -4px rgb(11 18 32 / 0.16), 0 2px 6px -2px rgb(11 18 32 / 0.08)",
        dialog: "0 24px 60px -12px rgb(11 18 32 / 0.35)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        "scale-in": { from: { opacity: "0", transform: "scale(0.97)" }, to: { opacity: "1", transform: "scale(1)" } },
      },
      animation: {
        "fade-in": "fade-in 150ms ease-out",
        "slide-up": "slide-up 180ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scale-in 120ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
