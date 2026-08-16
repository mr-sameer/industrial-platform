# Migrations

No models exist yet in Module 1, so there are no migration files under
`versions/`. Once Module 2+ declares ORM models against `app.db.session.Base`,
generate the first migration with:

```bash
cd apps/api
alembic revision --autogenerate -m "add users table"
alembic upgrade head
```
