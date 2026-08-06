# 0003 — FastAPI for the Backend Service

## Status
Accepted

## Context
The backend will eventually run AI/ML-adjacent workloads (industrial
trust scoring, procurement intelligence) alongside conventional CRUD and
needs first-class async I/O for talking to Postgres, Redis, and future
external AI services concurrently, plus automatic OpenAPI generation so
the web/mobile clients and this ADR set stay honest about the contract.

## Decision
FastAPI on Uvicorn, Python 3.12, fully async request handlers, Pydantic v2
for validation/serialization, SQLAlchemy 2.0 (async) + Alembic for
persistence.

## Alternatives considered
- **Django REST Framework**: batteries-included but sync-first ORM and
  heavier framework overhead for a service that's primarily a thin,
  fast JSON API in front of AI workloads.
- **Node.js/NestJS backend**: would let the whole stack be TypeScript, but
  Python's ecosystem (numerical/AI/ML libraries) is the better fit for
  this platform's AI-powered trust-scoring roadmap.
- **Flask**: lacks native async support and built-in validation/OpenAPI
  generation that FastAPI provides out of the box.

## Consequences
- OpenAPI docs are free at `/docs` (disabled in production — see
  `app/main.py`).
- Async SQLAlchemy requires care around session lifecycle (`app/db/session.py`
  uses `async_sessionmaker` with `expire_on_commit=False`).
- Alembic migrations must use the *sync* driver (`psycopg`) since Alembic's
  runner is sync — hence two DB URLs in config (`database_url` vs.
  `database_url_sync`).
