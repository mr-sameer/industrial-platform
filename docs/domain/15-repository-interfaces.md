# 15. Repository Interfaces

Repository interfaces are described here as **contracts** (what
operations exist and what they return, conceptually), not implementations
— no SQLAlchemy, no actual query code, per this document's scope. Each
maps to exactly one Aggregate Root (Section 5) — this is a deliberate
constraint (not, for example, a "CertificateRepository" for an entity
that isn't its own aggregate root) that keeps the repository layer's
boundaries matching the transactional boundaries already established.

## User Repository *(existing — Module 2/2.5)*
Already implemented (`app.services.auth_service`'s
`get_user_by_email`/`get_user_by_id` functions serve this role today,
even though not formally named/organized as a `UserRepository` class).
No change proposed; noted for completeness.

**Conceptual operations:** get by id, get by email, save (create/update),
list company memberships for a user (crosses into Company Repository
territory by id-reference only, not by loading the Company aggregate).

## Company Repository
**Conceptual operations:**
- `get_by_id(company_id) → Company | None`
- `get_with_members(company_id) → Company` (loads the full aggregate
  including `CompanyMember` rows)
- `save(company) → Company` (create or update, atomic with member-role
  invariant checks — Section 8)
- `list_by_owner(user_id) → list[Company]`
- `list_by_member(user_id) → list[Company]` (broader than owner — any
  membership role)
- `search_public_profiles(filters) → Page[Company]` (the *only* read path
  intended for Search Service's consumption — returns denormalized public
  fields, not the full aggregate, deliberately narrower than
  `get_with_members`)

## Product Repository
**Conceptual operations:**
- `get_by_id(product_id) → Product | None`
- `get_with_variants(product_id) → Product`
- `list_by_company(company_id) → list[Product]`
- `save(product) → Product`
- `search_published(filters) → Page[Product]` (same narrowness principle
  as Company Repository's `search_public_profiles`)

## Verification Repository
**Conceptual operations:**
- `get_by_id(verification_id) → Verification | None`
- `get_current_for_company(company_id) → Verification | None` (the
  currently-active verification record, if any — most common query
  shape, worth a dedicated method rather than always filtering a list)
- `list_history_for_company(company_id) → list[Verification]`
- `save(verification) → Verification`
- `list_pending_review(reviewer_role) → Page[Verification]` (the Platform
  Admin/Moderator queue — parameterized by role per Section 9's flagged
  Moderator-scope-for-Verification decision)

## Search Repository
**Conceptual operations:** deliberately **not** a thin wrapper over
Company/Product Repositories — this repository owns the denormalized
search index itself.
- `index_company(company_id, denormalized_data)` (write path, called by
  Search Service in response to domain events — Section 7/12)
- `index_product(product_id, denormalized_data)`
- `remove_from_index(entity_type, entity_id)`
- `query(search_query) → Page[SearchResult]` (the actual search
  execution — ranking logic, Section 12, applied here)
- `suggest(partial_input) → list[Suggestion]`

## AI Repository
**Conceptual operations:**
- `get_conversation(conversation_id) → AIConversation | None`
- `save_conversation(conversation) → AIConversation`
- `append_prompt(conversation_id, prompt) → Prompt`
- `save_recommendation(recommendation) → AIRecommendation`
- `list_recommendations_for_user(user_id) → list[AIRecommendation]`
- `save_risk_score(risk_score) → RiskScore`

**Explicitly does NOT expose:** any write operation touching Company/
Product/Verification tables — enforced at the interface-contract level
(the AI Repository's type signature simply has no such method), not just
by convention, so Section 11's non-coupling principle is structurally
guaranteed rather than merely documented.

## Repository design conventions (apply to all of the above)

1. **Every repository returns domain-shaped results, never raw rows** —
   consistent with the platform's existing pattern (Module 2.5's
   `session_service.py` returns `Session`/`RefreshToken` ORM-mapped
   objects, not dicts).
2. **Every "get" that can return nothing returns `None`, never raises**
   — matches the existing `get_user_by_email`/`get_user_by_id` convention
   (Module 2's `auth_service.py`); "not found" is a normal outcome, not
   an error, at the repository layer (the *service* layer decides
   whether "not found" should become a 404).
3. **List/search operations return paginated results**, not unbounded
   lists, for anything that could grow large (Companies, Products,
   Verification history) — a technical-debt-prevention concern (Section
   17) baked into the interface contract from the start rather than
   retrofitted after a performance incident.
