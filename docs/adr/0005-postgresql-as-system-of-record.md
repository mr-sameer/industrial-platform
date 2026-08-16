# 0005 — PostgreSQL as the System of Record

## Status
Accepted

## Context
The platform's eventual domain (industrial assets, procurement, trust
scoring) is fundamentally relational with strong consistency needs
(financial/procurement data cannot tolerate eventual-consistency
surprises), and will benefit from mature extensions (full-text/trigram
search, JSONB for semi-structured supplier data, PostGIS if geospatial
needs arise later).

## Decision
PostgreSQL 16 as the sole system of record, accessed via SQLAlchemy 2.0
async (`asyncpg` driver) at request time and via Alembic (`psycopg` sync
driver) for migrations. `pgcrypto` and `pg_trgm` extensions enabled by
default (see `infra/docker/postgres/initdb/001_extensions.sql`).

## Alternatives considered
- **MySQL/MariaDB**: viable, but weaker JSONB support and extension
  ecosystem compared to Postgres for this platform's anticipated
  semi-structured data needs.
- **MongoDB (document store) as primary store**: rejected — procurement
  and trust-scoring data has too many cross-entity relational integrity
  requirements to model comfortably as documents.

## Consequences
- No ORM models exist yet in Module 1 (`app/db/session.py` exports an
  empty `Base` with no mapped classes) — first real migration lands with
  the first business-feature module.
- Local dev and CI both run real Postgres via Docker (`docker-compose.yml`,
  `.github/workflows/ci.yml`) rather than SQLite, so behavior differences
  (e.g. `pg_trgm`) surface early.
