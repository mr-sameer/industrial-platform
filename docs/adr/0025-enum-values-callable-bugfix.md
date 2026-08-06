# 0025 — Fix: SQLAlchemy Enum Columns Must Set values_callable

## Status
Accepted — critical bugfix, affects every native-enum column in the
codebase (`user_role`, `session_revoked_reason`, and, as of this module,
`company_role`, `company_status`, `company_size`,
`company_verification_status`).

## Context
Discovered while building and testing Module 3A against a real,
Alembic-migrated database (not just the test suite's schema, which is
created via `Base.metadata.create_all` for speed — see
`tests/conftest.py`). Every hand-written Alembic migration in this
codebase defines native Postgres enum types with explicit **lowercase**
labels matching each Python enum's `.value`
(e.g. `sa.Enum("admin", "analyst", "viewer", name="user_role")`,
migration 0001). But `sqlalchemy.Enum(SomeEnumClass, ...)` — used by
every ORM model column (`Enum(Role, name="user_role", native_enum=True)`,
etc.) — **binds and generates DDL using each member's `.name` by
default, not `.value`**, even for `class Role(str, enum.Enum)` members
that are also literal `str` instances equal to their lowercase value
everywhere else in the codebase.

The result: two different sets of "valid" enum labels depending on how
the schema was created —
- Alembic (real deployments): lowercase (`admin`, `viewer`, ...)
- `Base.metadata.create_all` (this project's test suite): UPPERCASE
  (`ADMIN`, `VIEWER`, ...), since it derives DDL from the same
  (buggy-default) SQLAlchemy `Enum` object that also handles binding —
  making it internally self-consistent and silently passing every test,
  while broken end-to-end against any real, migration-created database.

This means **every user registration against a real deployment of this
platform would have failed** with `invalid input value for enum
user_role: "VIEWER"` — since Module 2, undetected, because no test in
this codebase had exercised the FastAPI app's actual registration
endpoint against an Alembic-migrated database rather than the
test-suite's `create_all` schema, until this module's development
process did exactly that (see the verification section below).

## Decision
`app.db.enum_utils.str_enum_values` — `values_callable=str_enum_values`
— added to every native-enum column definition across every model
(`user.py`, `session.py`, `company.py`, `company_member.py`), forcing
SQLAlchemy to bind and generate DDL using `.value` (lowercase),
matching every Alembic migration's hardcoded labels exactly.

`tests/conftest.py`'s schema-creation fixture was also affected
indirectly: the `company_members` single-Owner partial unique index
(`WHERE role = 'owner'`) is created via a plain **sync** (psycopg)
connection rather than the async engine, matching how Alembic creates
it — a related but distinct finding made while diagnosing this bug (see
that fixture's docstring for the full explanation of why the async path
specifically fails for this one statement even with correct enum
labels).

## How this was verified (not just fixed and assumed)
1. Confirmed the actual label mismatch directly via `pg_enum` on both a
   `create_all`-built test database (uppercase) and an Alembic-migrated
   dev database (lowercase) — the two didn't just theoretically differ,
   they were empirically confirmed different.
2. After adding `values_callable`, reset both databases from scratch and
   re-ran `alembic upgrade head` — all three migrations (0001–0003)
   apply cleanly.
3. **Started a real `uvicorn` server against the real, Alembic-migrated
   dev database** (not the test suite) and called `POST /auth/register`
   and `POST /companies` over real HTTP — both succeeded end-to-end,
   including the `CompanyRole.OWNER` enum value round-tripping correctly
   through creation, storage, and the API response (`"my_role": "owner"`).
4. Re-ran the full test suite (91 tests) from a freshly created test
   database — all passing, confirming the fix didn't regress the
   internally-self-consistent `create_all` path either.

## Alternatives considered
- **Change the Alembic migrations to use uppercase labels instead**:
  rejected — would require a data migration for any already-deployed
  database (none exist yet, but the principle holds for the future),
  and uppercase enum values in the database are a worse fit for JSON
  API responses (`docs/standards/naming-conventions.md` already
  establishes lowercase `snake_case`-flavored values as this platform's
  wire-format convention).

## Consequences
- Every future native-enum column **must** use
  `values_callable=str_enum_values` — flagged prominently in
  `app/db/enum_utils.py`'s own docstring, and worth adding to
  `docs/standards/coding-standards.md` as an explicit rule (tracked as a
  documentation follow-up, not done as part of this ADR to keep this
  entry focused on the incident itself).
- This is the second time in this project's history that a schema
  divergence between `Base.metadata.create_all` (tests) and Alembic
  (real deployments) has caused a bug invisible to the test suite — see
  migration 0001's note about duplicate enum-type creation, discovered
  the same way, in Module 2. Worth treating as a pattern: this project's
  test suite's `create_all`-for-speed tradeoff (documented and
  deliberate — see `tests/conftest.py`) has a real, recurring blind
  spot for schema-level bugs, not just an inconvenience. A periodic
  "run the actual migrations and smoke-test the live server" check —
  exactly what this module's development process did — is worth doing
  routinely, not just when a new module happens to prompt it.
