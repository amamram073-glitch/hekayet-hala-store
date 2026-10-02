# Containers

The root `docker-compose.yml` is the single source of truth for PostgreSQL, Redis, API, Celery worker, React web, and Nginx. Container definitions are next to their application code (`apps/api/Dockerfile`, `apps/web/Dockerfile`). Nginx proxies API and docs to FastAPI and all other routes to static React files served by Nginx with SPA fallback. Docker runtime was unavailable in the implementation environment; validate the Compose build and TLS termination on the deployment host before production use.
