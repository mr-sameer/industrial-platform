# Missing API — Frontend Integration Sprint

Per this sprint's rules: the backend is the single source of truth, and
no fake/mocked endpoints are invented. Anywhere the frontend needed data
or an action with no corresponding backend endpoint, it's listed here
instead of faked.

## 1. Notifications

**Why it's needed:** The Application Shell brief requires a
Notifications component. Checked `docs/architecture/openapi.json` (32
endpoints, Modules 1–3B) — there is no notifications resource anywhere
in the API, and no `AuditLog`-to-user-facing-notification translation
layer exists either (Module 2.5's `AuditLog` is an internal audit trail,
not a per-user notification feed).

**Priority:** Medium. The shell works correctly without it — the bell
icon renders a genuine, honest empty state ("You're all caught up")
rather than fabricated data, per this sprint's "no mocked business
data" rule. Becomes higher priority once there's a real source of
notification-worthy events a user would want pushed to them (e.g. "your
document was verified" once the admin-review workflow ADR-0029 deferred
actually exists).

**Suggested implementation:**
- A `notifications` table: `id`, `user_id` (FK), `type`, `title`,
  `body`, `link_url` (nullable), `read_at` (nullable), `created_at`.
- `GET /notifications` (paginated, filterable by read/unread),
  `PATCH /notifications/{id}` (mark read), `PATCH /notifications/read-all`.
- Emitted by whichever service action is notification-worthy — e.g.
  `company_service.add_member` could emit one to the invited user,
  a future document-verification action could emit one to the company's
  Owner/Admins. Natural fit alongside the existing `AuditLog` write in
  each of those call sites, not a new cross-cutting system.
- Real-time delivery (websocket/SSE) is a separate, larger decision —
  polling `GET /notifications?since=` on an interval is a reasonable
  first implementation and needs no new infrastructure.

## 2. Dashboard "Recent Activity"

**Why it's needed:** The Dashboard section of this brief asks for
"Recent Activity." The only data source that resembles this today is
`AuditLog` (Module 2.5) — but there is no endpoint exposing it to the
frontend at all; every existing `AuditLog` write happens purely
server-side for compliance/security purposes, and Module 2.5's ADR
explicitly designed it as an internal system, not a user-facing feed.

**Priority:** Medium — same reasoning as Notifications: the dashboard
works correctly without it (that section is simply omitted from Phase 2
rather than faked), but a real "what happened recently" view is a
natural, expected dashboard feature.

**Suggested implementation:**
- `GET /companies/{id}/activity` — paginated, returns a user-facing
  projection of relevant `AuditLog` rows scoped to that company (e.g.
  `member_joined`, `document_uploaded`, `company_updated`), with a
  human-readable label per event type, not the raw audit log shape
  (which includes fields like `metadata` blobs not meant for display).
- This is deliberately a **new read endpoint**, not exposing `AuditLog`
  directly — the audit log's shape and retention policy are a security
  concern (Module 2.5's ADR-0017) and shouldn't be coupled to what a
  dashboard widget wants to render.

## 3. Company logo/cover/branding on the search & public-profile list endpoints

**Why it's needed:** `GET /companies/search` (`CompanySearchResult`)
and the company-list endpoint (`CompanyPublic`) don't include
`logo_thumbnail_url` — only the individual company detail/branding
endpoints do (Module 3B). This means the Command Search palette and any
future company-card grid can't show a logo thumbnail without an
additional per-company request, which isn't practical at list scale.

**Priority:** Low-medium. Not a blocker — the Command Search palette
(Phase 1) uses a generic building icon instead, which is a reasonable,
honest fallback, not a broken feature. Worth doing before Phase 3
(Company Module) builds a visual company grid, where a missing logo
thumbnail will be more noticeable.

**Suggested implementation:** Add `logo_thumbnail_url: str | None` to
`CompanySearchResult` and `CompanyPublic` (both already `from_attributes`
Pydantic models reading from the `Company` ORM object, which already
has this column since Module 3B — this is a one-line schema addition on
the backend, not a new endpoint).

---

*No other gaps were found. Every other frontend requirement in this
sprint's brief (auth, company CRUD, verification, documents, branding,
social links) has a corresponding, already-implemented backend
endpoint — see `docs/architecture/openapi.json`.*
