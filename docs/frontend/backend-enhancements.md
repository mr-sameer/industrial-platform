# Backend Enhancements — ForgeX Public Homepage

Per the redesign brief: no backend implementation happens without
explicit approval. Everything below is documentation only.

The homepage was simplified to 5 sections (Hero+Search, AI Conversation
Demo, Trusted Companies, Why ForgeX, plus header/footer) after an
explicit product-direction pass rejecting the earlier, more
"directory-style" version — see the ADR referenced in the completion
report for the full before/after rationale. Several of the gaps below
(categories, trending searches, market-intelligence stats, product
catalog) are now moot for the homepage itself, since those *sections
were removed entirely* rather than kept as placeholders — the product
direction was explicit that browsing affordances don't belong on this
page at all, backed by real data or not. They may still matter for a
future dedicated page and are kept here for that reason.

| # | Feature | Reason | Suggested Endpoint | Priority | Module |
|---|---|---|---|---|---|
| 1 | **Natural-language / AI search** | The `/discover` page's "why" reasoning is real but deterministic — it runs the query as an independent substring match against name/industry/city/country (4 parallel calls to the unmodified `GET /companies/search`) and reports exactly which real fields matched, ranked by match count. Verified directly: a "Pune" query correctly ranked a 2-field match above a 1-field match, with accurate per-result reasoning. What's still missing: true intent parsing (e.g. "5,000 hydraulic cylinders" → quantity + product type), which no amount of client-side substring matching can honestly provide. | `POST /ai/search` — accepts free text, returns structured filters + a real generated explanation | High | A new AI/Search Intelligence module |
| 2 | **Product entity & search** | Company Profile → Product Profile → Compare (the brief's original vision) needs product-level data. No `Product` entity exists yet (Module 3B deferred it). No homepage section references this anymore (Featured Products was removed, not kept as a placeholder) — tracked here for whenever a dedicated Products page is approved. | `Product`/`ProductVariant` tables, `GET /products/search` | High | A future Products module |
| 3 | **Industry/category taxonomy + aggregation** | No "list distinct industries" or aggregate-by-category endpoint exists. Not currently needed by the homepage (Popular Categories was removed — AI Search is the only discovery path now), but relevant if a future Search Results or Industries page is built. | `GET /industries`, or `GET /companies/search/facets` | Medium | Ties into `docs/adr/0023`'s deferred taxonomy |
| 4 | **"Featured" / curated company flag** | `FeaturedCompanies` (now reframed as a "Trusted by" trust-signal row, not a browsable grid) still just shows the 5 most recently created companies — the only sort the API offers that approximates curation. No editorial "is_featured" flag exists. | Add `featured: bool` to `Company`, or a `sort_by=relevance` combining verification level + recency | Low | Company Core (Module 3A) — additive column |
| 5 | **Search analytics / trending queries** | No real query-volume data exists. Not currently needed — the "Trending Searches" section was removed entirely rather than kept as an illustrative placeholder, per the explicit "no browsing affordances" direction. | A `search_queries` log + `GET /analytics/trending-searches` | Low | A future Analytics module, if a Search Results page ever wants this |
| 6 | **Market intelligence / platform stats** | No real aggregation endpoint exists beyond `GET /companies/search`'s own `total` field (which the homepage no longer surfaces — the stat bar was removed for not building enough trust to earn its place). Worth revisiting once real aggregate stats exist. | `GET /analytics/platform-stats` | Low | A future Analytics module |

| 7 | **Human-readable labels for satisfied verification requirements** | `VerificationScorePublic.satisfied_requirement_keys` returns raw keys (e.g. `"owner_email_verified"`), not labels — unlike `missing_requirements`, which already includes a `label` field. The `/discover` page's trust signal works around this by showing only the overall level + percentage, not a per-requirement breakdown, to avoid needing a client-side duplicate of the label mapping. | Add the same `label`/`weight` shape to satisfied requirements, or a single unified `requirements: [{key, label, weight, satisfied}]` list | Low | Company Verification (Module 3B) — additive schema change to an existing response |

## The pre-existing routing issue — now resolved for public discovery

`apps/web/src/app/(app)/companies/search/page.tsx` still sits behind
the authenticated shell. This no longer blocks anonymous discovery,
though — `/discover` (new, this phase) is a fully public page and is
now the real, working answer to "how does an anonymous visitor search"
that the homepage's search bar and the old, auth-gated search page
could not provide. The old page's placement is still worth fixing
eventually (for consistency, not because anything is broken by it now),
but it's no longer the blocker it was flagged as.
