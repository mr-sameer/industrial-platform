-- Runs once, automatically, the first time the postgres container
-- initializes an empty data directory (see docker-compose.yml volume mount
-- of ./infra/docker/postgres/initdb into /docker-entrypoint-initdb.d).
--
-- Module 1 enables extensions that are near-universally useful for the
-- domains this platform will eventually cover (UUID PKs, trigram search
-- for fuzzy supplier/asset name matching). No tables are created here —
-- schema ownership belongs to Alembic migrations.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
