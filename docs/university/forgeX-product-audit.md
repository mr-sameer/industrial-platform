# ForgeX Product Audit

**Product & UX Dossier — No code changed**

A page-by-page and journey-by-journey audit of the live ForgeX frontend, run against the running application (Docker dev stack, hot-reloaded from the current working tree) and checked line by line against the *ForgeX Founder University* document. Nothing in this document was fixed — it's the "before" picture.

| | |
|---|---|
| **Date** | 2026-08-29 |
| **Journey tested** | Homepage → Register → Dashboard → Consult → Recommendation → Company profile → Companies → New Company → Products → Logout → Login |
| **Findings** | 27 discrete, all reproduced live or confirmed in source |
| **P0 / P1 / P2** | 5 / 8 / 6 |

**Bottom line:** the backbone the University document cares most about — deterministic extraction, evidence-cited recommendations, an honest "Unknown" state, a disciplined question ceiling — is real and mostly works. What's missing is everything the document spends less time on: the first-session Dashboard is a self-labeled placeholder, the Companies/onboarding module is visually a different, older product than Consult, and a realistic buyer sentence with a quantity in it ("I need 500 room heaters…") breaks the extraction pipeline the same way the University's own "Need 5,000 units" example says it must not.

**Structurally sound:** Requirement Intelligence never re-asks an answered question, stays under the University's four-question ceiling in every test run, and every recommendation traces back to a citable source with an honest Observed/Verified label — no fabrication observed anywhere.

**Structurally weak:** Three visually incompatible UI systems ship simultaneously (marketing/Consult, a bare inline-style "Module 3A" system, and one raw placeholder page), and the app's own source comments repeatedly self-describe pages as "minimal admin/testing," not finished product.

---

## Table of contents

1. [Methodology & limits](#00--methodology--limits)
2. [Buyer journey map](#01--buyer-journey-map)
3. [Page-by-page audit](#02--page-by-page-audit)
4. [Consult & Requirement Intelligence](#03--consult--requirement-intelligence)
5. [Company onboarding & verification](#04--company-onboarding--verification)
6. [Visual & design-system audit](#05--visual--design-system-audit)
7. [Responsive audit](#06--responsive-audit)
8. [University alignment matrix](#07--university-alignment-matrix)
9. [Prioritized issue list](#08--prioritized-issue-list)
10. [Recommended implementation order](#09--recommended-order)
11. [Now vs. future scope](#10--now-vs-future-scope)

---

## 00 / Methodology & limits

Everything below was exercised against `localhost:3000` / `localhost:8000` (the actual Docker dev stack, source-mounted with hot reload — this reflects the current working tree, including uncommitted changes) via real browser interaction, not static reading. Three limits are worth stating up front rather than silently working around:

- **Email verification blocked deeper account-holder pages.** A fresh registered account cannot create a company until its email is verified, and the dev environment's email sender only logs a subject and byte-length — never the token or link (`email_service.py:25`) — and the token itself is stored only as a one-way hash in Postgres. Business Information, Verification, Documents, Branding, Social Links, Products, and Offerings were therefore evaluated by reading their actual source and existing tests rather than by clicking through them as an authenticated owner. Every claim from source is labeled "code-reviewed" below rather than "observed live."
- **The viewport-resize tool did not actually resize the browser** in this session (`window.innerWidth` stayed at 1536px after every resize call). The responsive audit is therefore evidence-based from the stylesheet, not visually confirmed at real mobile widths — see §06.
- **The dev database has only three seeded product categories** (Bridal Lehenga, Jacuzzi Bathtub, Room Heater) and zero companies that were ever created through the real onboarding flow — every company record is ingested MCA/TradeIndia/IndiaMART pilot data. Several University examples (CNC machining, hydraulic cylinders) fail purely because that category doesn't exist yet, not because of a code defect — flagged as a data limitation, not a bug, throughout.

---

## 01 / Buyer journey map

Sequence tested (registration was tested after the anonymous Consult flow, matching how the running app actually gates the two — Consult works fully logged-out; company creation requires an account):

| Stage | Status |
|---|---|
| Homepage | 🟢 OK |
| Search submit | 🔴 P0 |
| Consult | 🟡 P1 |
| Recommendation | 🟡 P1 |
| Company profile | 🟢 OK |
| Register | 🟢 OK |
| Dashboard | 🔴 P0 |
| Companies | 🟡 P1 |
| New Company | 🟡 P1 |
| Business info / Verification | 🟡 P1 |
| Products | 🟡 P1 |
| Logout / Login | 🟢 OK |

🟢 = works as a buyer would expect. 🟡 = works but feels unfinished or discontinuous. 🔴 = breaks or dead-ends. Severity detail in §08.

---

## 02 / Page-by-page audit

| Page | Technical correctness | Product / UX quality |
|---|---|---|
| **Homepage** `P0` | Search submit throws a real, reproducible React `"Maximum update depth exceeded"` exception during typing (traced to the input's onChange path in `AISearchBar.tsx`); the page still navigates to Consult with the query carried in the URL. | Clean, honest three-point value prop ("Ask, don't browse" / "Real verification" / "Built for what's next"). The "Trusted by real companies" strip undercuts its own message: it shows raw MCA legal-entity names (*COSMIC WEALY PRIVATE LIMITED, DEEP GIFT CORNER PRIVATE LIMITED, TUK TUK IMPEX PRIVATE LIMITED*) with no logo, context, or explanation — reads as unfiltered scraped registry data, not curated social proof. |
| **Register** `Aligned` | Works correctly; password-strength validation rejects a common password with a clear inline message before allowing submission. | Minimal and unobjectionable — exactly as much screen as this step needs. |
| **First-session Dashboard** `P0` | Functions exactly as coded; no bug, no crash. | The page is a self-labeled placeholder in its own source: *"Placeholder protected page proving the auth flow end-to-end. Real dashboard content arrives with the first business-feature module."* A brand-new user's very first authenticated screen is unstyled system-font text reading "Signed in as… — role: viewer" and a bare "Log out" link. This is the single largest gap between the shipped product and "coherent, production-quality B2B SaaS." |
| **Consult (guided search)** `P1` | Works end-to-end for a seeded category (Room Heater); correctly skips any field the buyer already stated; fails whenever the stated quantity is fused to the product noun ("500 room heaters," "2000 valves") rather than in a "quantity: N" label format — see §03. | The chat itself reads well (clear assistant/user bubbles, chip-based quick answers). The composer is a single-line `<input>`, not a growing textarea, inside a visually large rounded/padded/shadowed bar — exactly the "big outer surface, cramped writing area" feel reported, most visible once a sentence runs past one line's width. |
| **Recommendation results** `Mostly aligned` | Renders correctly; every evidence line links to its real source (TradeIndia/IndiaMART seller profile); trust-tier and certification points match the documented scoring formula exactly. | The strongest screen in the app — genuinely evidence-first, no invented confidence. Undercut only by thin seed data: the one match returned was a 17.86%-match, one-employee general trading company (also selling wireless earphones and LED bulbs) labeled "Manufacturer." |
| **Company profile** `P2` | Loads correctly; carries the search's procurement context via a query-string JSON blob (functions, but the URL is very long and would degrade if copied/shared or bookmarked). | Appropriately humble about an unverified company (explicit "Unverified" badge, clear "not shown to other visitors" note on the carried-over match). But the page has almost nothing beyond that one match: no about section, no other offerings, no contact/RFQ action — a dead end, not a profile. |
| **Companies (list)** `P1` | Loads correctly; correct empty state; the sidebar nav item and the "Create your first company" button both silently no-op on the first click after a route change and require a second click. | A single bordered card with one sentence and one button in a sea of white space — functional but says nothing about what having a company on ForgeX unlocks. |
| **New Company** `P1` | Same first-click flakiness. The email-verification requirement is enforced only *after* the entire multi-field form is filled out and submitted — surfaced as one small red line below the fold: "Please verify your email address before continuing." | A reasonably organized single form (name, legal name, description, industry, contacts, size, GST, location). Correctly leaves CIN/PAN/MSME/IEC for a later step rather than cramming everything here — see §04. |
| **Business Info / Verification / Documents / Branding / Social Links** `P1 (code-reviewed)` | Business Information correctly persists CIN, GSTIN, PAN, MSME number, IEC number, and registration date; the Verification hub correctly links out to Business Info and Documents as separate steps rather than one mega-form. | Rendered entirely with the plain `ui-styles.ts` inline-style module, not the Tailwind design system used everywhere else — bare native `<select>`/`<input>` controls, no section grouping, no microcopy explaining why a founder should bother supplying an IEC number. See §05. |
| **Products / Offerings** `P1` | Loads a real, correctly styled list against the live Product Graph via `GET /products/search`. | Self-labeled in its own source comment: *"Phase 4B minimal admin/testing page… Not a polished public page — an internal view… for verifying and browsing what's actually in the system."* It ships on the same authenticated sidebar as every real feature, indistinguishable to a user from a finished one. |
| **Discover** `P0` | Loads, debounces, and paginates correctly against `GET /companies/search` — which only matches company name/industry/city/country. It has no awareness of what a company sells. | Searching "room heater" here returns "0 found," while the same term matches a real company through Consult seconds later. ForgeX effectively ships two disagreeing search experiences under one product. |
| **Logout / Login** `Aligned` | Logout needed a second click to register (same first-click flakiness as above) but then correctly cleared the session and redirected to `/login?next=/dashboard`; login correctly honored `next` back to the origin page. | Clean and consistent with Register — no complaints. |

---

## 03 / Consult & Requirement Intelligence

Four inputs were run start to finish: one long and quantity-heavy, one copied verbatim from the University's own Lesson 7 example, one detailed-but-realistic, and one single word.

| Buyer said | Questions asked | Product/category extracted | Quantity extracted | Outcome |
|---|---|---|---|---|
| "I need 2000 stainless steel ball valves for a water treatment plant" | 3 (role, country, certs) | "2000 stainless steel ball valves for a water treatment plant" — **raw, unparsed** | Unknown — **missed** | Dead end: *"I don't recognize '…' as a product category ForgeX tracks yet."* |
| "Need CNC machining in India" *(University Lesson 7's own example)* | 1 (role — country correctly not re-asked) | "CNC machining" — **clean** | n/a | Dead end anyway — "CNC machining" isn't a seeded category (**data gap**) |
| "I need 500 room heaters for a hotel chain, ISO certified, within 45 days" | 2 (role, country — certs & timeline correctly not re-asked) | "500 room heaters for a hotel chain, certified" — **quantity + purpose clause leaked in** | Unknown — **missed** | Succeeds anyway — category resolution tolerated the noise and matched "Room Heater"; returned 1 real, correctly-scored result |
| "heaters" | 1 (role) | "heaters" | n/a | Proceeds correctly — the minimal case works fine |

### What this shows precisely

Two independent things are true at once, and it's worth keeping them separate rather than blaming one bug for both:

- **Category resolution is more tolerant of noisy text than quantity extraction is.** "500 room heaters for a hotel chain, certified" still matched the real "Room Heater" category despite the mess — that's a genuinely resilient piece of matching. But in every single test, a quantity fused to the product noun ("I need 500 X," "2000 X") was never pulled out — `Quantity: Unknown` every time, even though the number was stated in plain language in the buyer's very first message. The previous fix (commit `938284c`) demonstrably handles the literal label format `"quantity 500, budget 20000 USD, timeline 2 months"` it was tested against, but not the natural phrasing a real buyer actually types.
- **The CNC-machining dead end is a pure data gap, not a code defect.** Extraction was perfectly clean ("CNC machining"); the category genuinely doesn't exist in the three-category dev catalog (Bridal Lehenga / Jacuzzi Bathtub / Room Heater). Worth fixing before any live demo, since it's the University document's own running example.

### The four-question ceiling

Across all four runs, the assistant asked at most 3 questions and never once re-asked a field the buyer had already stated (role was always asked since it's genuinely never given; country, certifications, and timeline were each skipped correctly whenever already present in the original sentence). This matches Lesson 7 exactly:

> "The architecture deliberately has a four-question ceiling. The system should ask only questions that materially improve the search."
> — *ForgeX Founder University* — Lesson 7, "AI Search & Requirement Intelligence," §3

### The "premade text" feeling — root cause

Consult's own input never pre-fills a message; the placeholder is a normal empty-state hint ("e.g. Need CNC machining in India"). The actual source is the **homepage's** rotating example text (`AISearchBar.tsx`'s `ROTATING_PROMPTS`, cycling every 2.8s) combined with the same component's onChange bug (§02, §08) — a buyer typing over an actively-animating placeholder, in a component that's already been observed throwing a render-loop exception on input, is a plausible and fixable source of the "artificial" feeling, rather than Consult itself showing scripted conversation history.

### The composer proportions

Confirmed in source: both the homepage search bar (`AISearchBar.tsx:115-125`) and the Consult composer (`consult/page.tsx:446-452`) use a single-line `<input>`, not an auto-growing `<textarea>`, wrapped in a visually generous rounded/padded/shadowed pill. For a short query this looks fine; for the University's own longer worked example — *"I need a manufacturer near Delhi who can produce 5,000 stainless-steel hydraulic cylinders within 30 days, preferably ISO-certified"* — the text scrolls sideways inside one fixed-height line while the outer chrome stays exactly as large, which is precisely the "big surface, cramped writing area" feel reported.

---

## 04 / Company onboarding & verification

The underlying architecture already does what was asked — it just doesn't show its work.

**What's correctly separated:** Company identity (name, industry, contacts, location) lives in `/companies/new`. Legal/registration identifiers — CIN, GSTIN, PAN, MSME, IEC, registration date — live one step later on `/companies/[id]/business-info`. Documents (certificates, registration evidence) are their own page. The Verification hub links out to both as distinct cards rather than one long form. This matches the separation asked for almost exactly.

**What's missing around that separation:** Nothing on the New Company form or the empty Companies list tells a founder that a second step exists, or why it matters. A founder could plausibly finish the first form, see their company appear, and never learn that an unverified "Email Verified"-only listing is worth almost nothing on a platform whose entire pitch is evidence-based trust.

### Verification economics, per the University document

> "ABC says it has 10 CNC machines. That's a claim. ForgeX may find evidence. Then a reviewer checks the evidence… But verification has a cost… That's why you cannot verify everything manually from day one… So ForgeX shouldn't treat every field equally. We need: LOW RISK / MEDIUM RISK / HIGH RISK, and verification effort should reflect that."
> — Lesson 4 ("How ForgeX's Data Becomes Its Moat"), §9–10 — CIN is used as the document's own example of a "much more important" high-value field

The shipped Business Information form does collect exactly the high-value identifiers the document names (CIN chief among them) — but presents CIN, GSTIN, PAN, MSME, and IEC as five equally-weighted plain text boxes with no indication that some matter more than others for trust, and no explanation of what a CIN even is to a first-time founder. The risk-tiering the document asks for exists in the data model's intent, not in the page.

### Trust/verification concern found live

The one real recommendation surfaced during testing was `SN PHINICS PRIVATE LIMITED` — a "Members: 1" company whose own scraped seller profiles list Room Heaters alongside Wireless Earphones, Bluetooth Earphones, and LED Bulbs — shown with a "Manufacturer" role tag and an "Email Verified" trust badge. The homepage promises *"Companies are evidence-based verified — not self-reported badges,"* but nothing on the profile substantiates the manufacturer classification specifically; it appears to be an unverified, self-declared attribute carried through the match rather than something the trust score actually checked.

---

## 05 / Visual & design-system audit

This isn't a matter of taste — it's confirmed directly in the code's own comments and a real, documented design system that large parts of the app never adopted.

| System | Where it's used | Evidence |
|---|---|---|
| **Tailwind + design tokens** (the real system) | Homepage, Consult, public company profile, AppShell/Sidebar/TopBar, Discover, Products list | `docs/architecture/design-system.md` — a genuinely considered system: Graphite Navy sidebar, Blueprint Blue `#2F6FEE` accent, a five-tier gray→gold verification-color progression, Inter for chrome, Space Grotesk for display, and **IBM Plex Mono specifically for GSTIN/PAN/CIN values**. |
| **Plain inline styles** ("Module 3A convention") | Companies list, New Company, Business Info, Verification, Documents, Branding, Social Links, Settings — 10 pages, all of the account-holder company-management module | Self-documented in `ui-styles.ts:3-13`: *"Minimal shared inline-style constants for Module 3A's company pages… rather than introducing a CSS framework for this module."* Uses a dark-green `#1a3c34` button color that appears nowhere in the design-system doc's actual palette. |
| **Raw, unshared inline styles** (no system at all) | The first-session Dashboard | Doesn't even import `ui-styles.ts` — literal `style={{ fontFamily: "ui-sans-serif…", padding: "3rem" }}` on a bare `<main>`, per its own "placeholder" comment. |

Login and Register use a blue primary button that's close to the documented Blueprint Blue accent; the Companies module's dark-green button and the Dashboard's total absence of styling are the two clearest tells that this part of the app was built to a different, earlier standard and never revisited once the newer system existed.

### Other visual/interaction notes

- **First-click flakiness** — the Companies sidebar nav item, "Create your first company," and Logout each silently did nothing on the first click immediately after a route or auth-state change, requiring a second click. Small, but repeated four separate times across a ten-minute session is a real, felt papercut.
- **Match-percentage precision** — recommendations show scores like "17.86% match" to two decimal places on a single result; whole-number rounding would read as more considered and less like raw formula output.

---

## 06 / Responsive audit

The browser-automation resize tool did not change the actual rendered viewport in this session (confirmed via `window.innerWidth` staying at 1536px after every resize call) — flagging this rather than fabricating a visual mobile pass.

**Evidence of real responsive work:** The AppShell has a genuine mobile drawer (`MobileNav.tsx`, Radix Dialog, `md:hidden` on the trigger, reusing the same `NavLinks` as the desktop sidebar rather than duplicating them) and the Consult page applies `sm:px-6` responsive padding to its header, main, and composer.

**Where breakpoints are absent:** The homepage (`app/page.tsx`) and its search bar component contain zero `sm:`/`md:`/`lg:` classes — built with fluid flex/max-width containers, which often reflows acceptably by default but was not visually confirmed at a real mobile width in this session.

*Recommendation: re-run this section with an actual device-width screenshot pass before treating it as closed.*

---

## 07 / University alignment matrix

| Principle | University citation | Status | Evidence |
|---|---|---|---|
| Ask only when missing *and* materially useful; four-question ceiling | Lesson 7, §3 | **Aligned** | Max 3 questions asked in every test; never re-asked an answered field. |
| Deterministic extraction — no fabricated quantity/budget | Lesson 7, §8 ("Need 5,000 units" → quantity=5000, never guessed) | **Gap** | Never fabricates, but also never extracts — "I need 500 room heaters" yields Quantity: Unknown despite the doc's near-identical worked example. |
| Honest "Unknown" state; Verified/Claimed/Observed vocabulary | Lesson 7, §17–18 | **Aligned** | RecommendationCard shows "Unknown" for quantity/budget/timeline and "no VERIFIED evidence found" for certifications rather than guessing. |
| Evidence-aware, cited recommendations (Fact→Evidence→Signal) | Lesson 7, §7 & §14; 7A-2 doc §7 | **Aligned** | Every signal in the live card cites a real, clickable source (TradeIndia/IndiaMART) and a trust-tier point breakdown matching the documented 50/30/20 formula exactly. |
| Certification signal conservative until admin review exists | 7A-2 doc §9 (ADR-0029 not yet built) | **Aligned (by design)** | Certifications scored 0/20 for the only live match — correct, documented v1 behavior, not a bug. |
| Search becomes a conversation, not "search box → results" | Lesson 7, §23, §26; Lesson 10, §37 | **Gap** | Homepage→Consult is a hard page navigation to a new URL with different chrome — functionally continuous, not experientially continuous. |
| "The website should evolve around the customer workflow, not the database architecture" | Lesson 10, §36 | **Gap** | /products is self-labeled "minimal admin/testing," and the Dashboard is a self-labeled placeholder — both ship on the real customer-facing nav. |
| Old keyword search is what ForgeX is explicitly moving away from | Lesson 7, §1 | **Gap** | /discover keeps a first-class, actively maintained pure keyword-search route alive, disconnected from the Product Graph that powers Consult. |
| Website ≠ verification; company-provided ≠ independently verified | Lesson 5, §6–7 | **Aligned** | Company profile correctly badges "Unverified" and labels scraped seller-profile data "Observed," never "Verified." |
| Not every field deserves equal trust; risk-tiered verification effort | Lesson 4, §9–10 (CIN named explicitly) | **Trust limitation** | CIN/GSTIN/PAN/MSME/IEC are all collected but presented as equally-weighted plain fields with no risk framing or explanation. |
| AI interprets; deterministic systems enforce; LLMs never become the source of truth | Lesson 13, Rules 1 & 3 | **Aligned** | No fabricated confidence or invented facts observed anywhere in the live recommendation flow. |
| Global/every-category data ingestion | Lesson 10, §32 (explicit "don't build yet") | **Future scope** | Only 3 categories seeded — expected at this stage per the document itself, not a defect. |
| RFQ workflow, agents, graph-aware ranking | Lesson 7, §27 (marked ⏳, not yet built) | **Future scope** | None of these exist yet — correctly out of scope for this audit. |

---

## 08 / Prioritized issue list

| Sev | Finding | Where |
|---|---|---|
| **P0** | Homepage search bar throws a real React "Maximum update depth exceeded" exception during normal typing. | `AISearchBar.tsx onChange` |
| **P0** | Quantity is never extracted when fused to the product noun ("I need 500 X," "2000 X") — only the literal "quantity: N" label format works; this dead-ends realistic buyer sentences. | `lib/requirement.ts` |
| **P0** | First-session Dashboard is a self-labeled placeholder shown immediately after the highest-intent action (registering). | `app/(app)/dashboard/page.tsx` |
| **P0** | /discover only searches company name/industry/city/country — cannot find a company by what it sells, disagreeing with Consult on the exact same term. | `lib/discover.ts, companies.py:150` |
| **P0** | University's own flagship teaching example ("CNC machining in India") fails end-to-end live — category doesn't exist in dev data. | data gap |
| **P1** | Homepage→Consult is a hard page navigation with no shared visual continuity — structurally the "sudden transition" reported. | `app/page.tsx → /consult` |
| **P1** | Composer is a single-line input, not a growing textarea, inside a visually large pill — the reported proportion problem. | `consult/page.tsx:446-452` |
| **P1** | Homepage's rotating example placeholder + its onChange bug are the likely source of the "premade text" feeling. | `AISearchBar.tsx` |
| **P1** | New Company enforces the email-verification requirement only after a full form submit, shown as one small line below the fold. | `companies/new/page.tsx` |
| **P1** | Dev environment cannot complete any email-verification-gated flow without direct DB access — token never surfaced anywhere retrievable. | `email_service.py:25` |
| **P1** | Three incompatible visual systems ship at once (Tailwind / ui-styles.ts / raw inline) across the authenticated app. | `ui-styles.ts:3-13` |
| **P1** | /products is a self-labeled "minimal admin/testing page," shipped indistinguishably from finished features. | `products/page.tsx:12-17` |
| **P1** | Repeated first-click flakiness on nav items and primary buttons right after a route/auth change. | Companies nav, New Company CTA, Logout |
| **P2** | Company profile's carried-over match context is encoded as a large JSON blob in the URL query string. | `company/[slug]/page.tsx` |
| **P2** | Company profile has nothing beyond the one carried-over match — no about, offerings, or contact/RFQ action. | `/company/[slug]` |
| **P2** | Companies list and New Company screens are functionally correct but extremely bare — no explanatory copy. | `/companies, /companies/new` |
| **P2** | Match-percentage shown to two decimals ("17.86% match") on a single result. | `RecommendationCard.tsx` |
| **P2** | Business Information presents CIN/GSTIN/PAN/MSME/IEC as five equal plain fields with no risk-tier framing or explanatory copy. | `business-info/page.tsx` |
| **Trust** | A one-employee general trading company (also selling earphones/LED bulbs) is labeled "Manufacturer" with no verified evidence behind that specific role. | `/company/sn-phinics-private-limited` |
| **Data** | Only 3 seeded product categories exist; zero companies were ever created through the real onboarding flow — the entire authoring UI is essentially unexercised with real data. | dev DB seed |

---

## 09 / Recommended order

1. **Fix the AISearchBar render-loop and quantity extraction together.** Both live in the same conversion-critical path (homepage search → Consult), both are P0, and the extraction fix is what makes the University's own teaching examples usable for internal demos.
2. **Seed "CNC machining" and a couple of other University-example categories.** Cheapest possible fix, unblocks demoing the product against its own founder-training document.
3. **Replace the Dashboard placeholder with a real (even minimal) first-session view.** Doesn't need to be ambitious — a "your account" summary plus a clear path into Consult and Companies would already close most of the gap.
4. **Give /discover access to product/offering data, or remove it as a distinct entry point.** Two search experiences that disagree with each other on the same query is worse than one.
5. **Port the Companies/onboarding module onto the real design system.** Ten pages, but they share one style module (`ui-styles.ts`) — a single conversion pass fixes all of them at once.
6. **Surface the email-verification step earlier, and log verification links in dev.** Both are small: a banner/redirect before the New Company form, and one extra field in the existing stub-email log line.
7. **Widen the composer to an auto-growing textarea on both the homepage and Consult.** Small CSS/markup change, directly answers the reported proportion complaint.

---

## 10 / Now vs. future scope

**Fix now:** Everything in §08 marked P0 or P1, plus the Trust-limitation finding — none of these require new architecture, and several (the render-loop bug, the placeholder examples, the verification-token logging) are one-file changes.

**The University says: not yet** — RFQ workflow, autonomous agents, graph-aware ranking, global/every-category data ingestion, a dedicated graph database, and category-tree traversal are all explicitly named as deliberately deferred (Lesson 7 §27, Lesson 10 §32, 7A-2 §14/§16) — none of their absence is a finding in this audit.

---

*ForgeX Product & UX Audit — compiled 2026-08-29. No code, schema, or data was modified in the course of this review.*
