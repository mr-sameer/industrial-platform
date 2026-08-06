# infra/docker

Supporting files consumed by `docker-compose.yml` at the repo root:

- `postgres/initdb/` — SQL scripts run once against a fresh Postgres data
  volume (via Postgres's own `/docker-entrypoint-initdb.d` mechanism).
- `redis/` — reserved for a custom `redis.conf` if/when default settings
  stop being sufficient (e.g. maxmemory policy tuning).

Application Dockerfiles live next to the app they build
(`apps/web/Dockerfile`, `apps/api/Dockerfile`), not here — this directory
is only for infrastructure-level config that isn't specific to one app.
