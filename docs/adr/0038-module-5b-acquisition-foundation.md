# 0038 — Module 5B: Industrial Data Acquisition Foundation

## Status
Accepted.

## Context
Implements the first acquisition layer on top of Module 5A (frozen,
commit `80f4335cb6ce693e21198992bfd2ac2e0f6134ce`) per
`docs/product/phase-5-industrial-data-acquisition-architecture.md`'s
"controlled acquisition framework" scope. Strictly the foundation: a
collector abstraction, a job lifecycle, idempotency, retry handling,
and one deterministic test adapter — no real external source, no
scraping, no AI extraction, no entity resolution, matching this
phase's own explicit exclusion list.

## Decisions

1. **Exactly two new tables**, reusing Module 5A's `SourceRegistry`
   and `RawObservation` unchanged: `acquisition_jobs` (the controlled
   lifecycle) and `acquisition_job_events` (per-item outcomes —
   created / skipped_duplicate / failed). Neither
   `source_registry`/`raw_observations`/`provenance_records`/
   `data_conflicts` was touched; `acquisition_jobs.source_id` and
   `acquisition_job_events.raw_observation_id` are new *outbound* FKs,
   not columns added to Module 5A's tables.
2. **The job↔observation link lives on the new `AcquisitionJobEvent`
   table, not on `RawObservation`.** Module 5A's `RawObservation` has
   no `job_id` column and none was added — "what acquisition job
   produced this observation" is answered by querying
   `acquisition_job_events.raw_observation_id`, preserving Module 5A
   exactly as frozen.
3. **The data trust rule is enforced by omission, not a check.**
   `acquisition_service.py` never imports or calls
   `provenance_service.create_provenance_record` or
   `verify_provenance_record` — there is no code path in this module
   that can produce a `ProvenanceRecord`, verified or otherwise.
   Confirmed by a test that fetches a created observation through
   Module 5A's own route and gets `404` for any provenance record.
4. **Idempotency key: `source_id` + `external_identifier` (primary),
   `source_id` + `content_hash` (fallback only when an adapter
   provides no external identifier).** Documented explicitly, not just
   implemented: content_hash is never used un-scoped to a source, since
   two different sources could produce byte-identical content for two
   genuinely different real-world records. Proven with a dedicated
   test showing two different sources' identical fixture content are
   *not* treated as duplicates of each other.
5. **Bounded retry (`MAX_RETRIES = 3`), and the retryable/non-retryable
   distinction is the adapter's own responsibility** —
   `RetryableCollectorError` vs. `NonRetryableCollectorError`, two
   exception types a `SourceAdapter.collect()` implementation raises
   explicitly, rather than the acquisition service trying to guess
   from exception type or message content. `MockSourceAdapter` exposes
   both deterministically via `simulate_failure` config values, letting
   tests exercise each path without any real network flakiness.
6. **A job with zero created, zero skipped, and at least one failed
   item is honestly FAILED, never SUCCEEDED with a misleadingly empty
   result.** A job with a genuine mix (some created, some failed) is
   SUCCEEDED with a non-zero `failed_count` — the job status reflects
   whether the run overall produced anything usable, while
   `failed_count`/the per-item events preserve the honest, granular
   picture underneath.
7. **Job execution is synchronous within the creating request.** No
   background task queue exists yet — an explicit, documented
   limitation (see below), not an oversight. `PENDING` is set,
   immediately followed by `RUNNING`, followed by a real terminal
   state, all within one HTTP request/response cycle.
8. **RBAC: `Role.ADMIN` only, for every route in this subsystem,
   including reads.** Stricter than Module 4B/5A's "any authenticated
   user" pattern for Product/Provenance, because job creation is the
   one action in this whole codebase that actually executes code
   (an adapter's `collect()`) server-side, not just writes a row —
   matching the ticket's explicit "do not allow arbitrary users to
   execute arbitrary collectors."
9. **Secret redaction via a fixed key-name denylist**
   (`app/collectors/secrets.py`), applied to `requested_scope` before
   it's ever persisted to `acquisition_jobs.requested_scope` or
   embedded in any `error_message` — deliberately simple, matching the
   ticket's own instruction not to build a secrets-management platform
   this phase doesn't need yet (no real adapter has real credentials).

## Verification
- Migration `0007` run for real: upgrade → downgrade → re-upgrade, all
  clean.
- Real, manual end-to-end API proof (not just automated tests): created
  a source, ran a job (3 created), ran the identical job again
  (0 created / 3 skipped, database row count unchanged), triggered a
  retryable failure (retry_count=3, FAILED), a non-retryable failure
  (retry_count=0, FAILED), an invalid-config failure
  (`started_at=null`, never reached RUNNING), and confirmed a fake
  `password` value never appeared anywhere in the response while
  showing `***REDACTED***` in its place.
- 17 new automated tests (`tests/test_acquisition.py`), covering every
  item in the ticket's minimum-coverage list. Full backend suite:
  **189/189 passing** (172 pre-existing + 17 new), `ruff`/`mypy --strict`
  clean across all 88 backend source files.
- Frontend `tsc`, ESLint, Vitest (12/12, untouched), and a production
  build all clean — route list and bundle sizes byte-identical to
  before this module, confirming zero frontend impact (this module is
  backend-only, per the ticket's explicit instruction).

## Known limitations (explicitly not deferred silently)
- **No background task queue.** Every job runs synchronously inside
  the HTTP request that creates it — fine at this phase's scale (a
  handful of deterministic mock-adapter items), not appropriate once a
  real, slower adapter (a real website/API) is added. A future phase
  needs a real queue before any real collector is connected.
- **No per-source rate/concurrency/timeout policy enforcement** beyond
  the abstraction boundary (`SourceAdapter.validate_config`,
  `requested_scope`) — the ticket explicitly scoped this phase to "the
  abstraction/configuration boundary, not web-scale scheduling."
- **Only one registered collector type (`mock`).** `app/collectors/registry.py`
  is the extension point; adding a real adapter (website, API,
  structured file) is a new class + one registry entry, not a change
  to `acquisition_service.py`.

## Consequences
No architectural deviation from the approved Module 5B scope.
`docs/product/phase-5-industrial-data-acquisition-architecture.md`
was not modified. Module 5A remains untouched and frozen.
