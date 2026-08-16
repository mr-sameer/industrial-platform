# Design System — Frontend Integration Sprint

## Design plan (see `frontend-design` skill's brainstorm/critique process)

**Subject:** ForgeX — an AI industrial intelligence platform, and a B2B trust and
verification layer for industrial suppliers and buyers. The design's
job is to make "genuine, verified, trustworthy" feel true at a glance,
without looking like enterprise ERP software.

**Color** (4–6 named values, CSS custom properties in `globals.css`):
- `Canvas White` `#FFFFFF` / `Surface Gray` `#F7F8FA` — the light
  content area.
- `Graphite Navy` `#0B1220` — the dark sidebar. A hybrid layout (dark
  nav rail + light canvas), not full dark mode and not light-
  everywhere — a specific, deliberate choice, not the "near-black +
  single accent" AI-generated default (that pattern goes full dark;
  this stays majority-light).
- `Blueprint Blue` `#2F6FEE` — the accent. Named and chosen for the
  subject: the color of engineering and architectural line drawings,
  the most concrete visual shorthand for "industrial precision"
  available, and distinct from both generic Bootstrap blue (`#0d6efd`)
  and generic Tailwind indigo (`#4f46e5`).
- A cool-to-warm **verification-level progression**
  (gray → blue → indigo → violet → **gold**) mapped exactly to the
  platform's real 5-tier system (unverified → email → business →
  factory → premium), so "Premium Verified" earning a gold tone is
  earned by the platform's actual domain model, not an arbitrary
  palette pull.

**Type:** Inter for all UI chrome and body text (the readable SaaS
standard). **Space Grotesk** reserved for large display headings only —
used with restraint, not applied to every label, per the skill's
explicit guidance. **IBM Plex Mono** for data — GSTIN/PAN/CIN values,
IDs, timestamps — chosen because Plex's own design ethos ("engineered,
not decorated") fits a B2B industrial-data platform thematically, not
just functionally.

**Layout:** Fixed dark sidebar (desktop) / drawer (mobile, same nav
list, no duplication — see `Sidebar.tsx` exporting `NavLinks` for reuse
by `MobileNav.tsx`) + light canvas. Hairline borders (`--color-border`)
do most of the structural work, not box-shadows — shadows
(`shadow-popover`, `shadow-dialog`) are reserved for floating layers
only (dropdowns, dialogs, the command palette), matching Stripe/Linear's
flat precision rather than a "cards with drop shadows everywhere" look.

**Signature element:** A real, functional ⌘K command palette
(`CommandSearch.tsx`) searching live companies via the existing,
unmodified `GET /companies/search` endpoint. Chosen because it's
genuinely useful (not decorative), it's the single most recognizable
"Linear/Vercel" interaction pattern available, and it ties directly to
the platform's actual search capability rather than being an empty
UI flourish.

**Self-critique against the AI-default checklist** (see the skill's
calibration section): not warm-cream-plus-terracotta; not full
near-black-plus-acid-accent (this stays hybrid, majority-light); not
broadsheet-serif. The one deliberate risk taken: a dark sidebar against
a light canvas is a specific compositional choice with real tradeoffs
(the ProfileMenu and mobile-topbar NotificationsMenu must be styled for
a dark background specifically — see `NotificationsMenu`'s `variant`
prop — while the desktop topbar's NotificationsMenu needs the light
variant; this is why that component takes a variant prop instead of one
fixed style, a real bug caught during Phase 1's own build, not a
theoretical one).

## Tokens

See `apps/web/tailwind.config.ts` for the full Tailwind extension and
`apps/web/src/app/globals.css` for the actual CSS custom property
values. Semantic names (`canvas`, `surface`, `sidebar`, `ink`, `accent`,
`success`/`warning`/`danger`, `level-*`) rather than raw palette names,
so a future theme (e.g. dark mode for the canvas too) would only mean
changing the custom property values, not every component's classes —
not building that now, just not foreclosing it.

Radius: `sm` 6px (small controls), default/`md` 8px (buttons, inputs),
`lg` 12px (cards), `xl` 16px (dialogs) — a consistent, moderate system;
never 0 (avoids the "broadsheet" look) and never pill-shaped by default
(avoids the generic-rounded-SaaS look) except where actually
appropriate (avatars, badges).

## Fonts: a real environment finding

`next/font/google` requires build-time network access to
`fonts.googleapis.com`. This sandbox (and potentially some deployment
environments) has no such access — confirmed by a real failed build,
not assumed. Switched to `@fontsource/*` packages instead: the actual
font files ship inside the npm package, so there is zero external
network dependency at build or runtime, in any environment. This is
strictly more robust than `next/font/google`, not just a workaround for
this sandbox.

## Accessibility floor (see `globals.css`)

- Visible `:focus-visible` outline on every interactive element,
  platform-wide — not per-component.
- `prefers-reduced-motion: reduce` collapses every animation/transition
  to near-zero duration, respected globally via a media query, not an
  opt-in per component.
- Every icon-only control (`NotificationsMenu`, `MobileNav` triggers,
  the mobile close button) has an explicit `aria-label`; decorative
  icons are `aria-hidden`.
- `CommandSearch` and `MobileNav` use Radix `Dialog` — real focus
  trapping, `Escape`-to-close, and return-focus-on-close, not hand-
  rolled (hand-rolled dialog focus management is a common, easy-to-get-
  wrong accessibility failure this sprint deliberately avoided by using
  a correct, tested primitive).
- `ProfileMenu` and `NotificationsMenu` use Radix `DropdownMenu` for the
  same reason — correct roving-focus keyboard navigation (arrow keys,
  `Home`/`End`, type-ahead) without hand-rolling it.

## Application shell integration

`src/app/(app)/layout.tsx` wraps `dashboard`, `companies`, and `account`
routes with `AppShell` via a Next.js route group (doesn't change any
URL). `src/app/company/[slug]` (the public profile) and
`src/app/(auth)/*` are deliberately outside this group — a public page
and the login/register flow shouldn't render an authenticated sidebar.
Verified: a complete `next build` with all existing routes still
present at their original paths, plus a real register → login →
authenticated-request flow against a live server confirming the shell's
component tree (`AppShell`, `AuthProvider`) is correctly server-rendered
into the page's initial payload.
