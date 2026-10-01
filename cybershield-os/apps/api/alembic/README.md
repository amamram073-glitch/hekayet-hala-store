# Database migrations

Run from `apps/api` after configuring `DATABASE_URL`:

```bash
alembic upgrade head
alembic current
```

Development auto-creates missing tables for convenience only. Production should apply Alembic before starting the API.