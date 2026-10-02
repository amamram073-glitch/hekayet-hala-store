from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import time
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy import text
from uuid import uuid4
from app.config import settings
from app.db import Base, engine
from app.routes import analyst, analytics, api_keys, assets, auth, cases, dashboard, events_soc, evidence, findings_risks, incidents_events, notifications, ops, realtime, reports, retention, search, team, threat_intel, webhooks
from app.security import check_csrf

_access_log = logging.getLogger("cybershield.access")


def _apply_rate_limit(request: Request):
    if settings.environment != "production" or not request.url.path.startswith("/api/"):
        return None
    path = request.url.path
    if path == "/api/auth/login": limit, window = 10, 60
    elif path == "/api/auth/register": limit, window = 5, 3600
    elif path == "/api/webhooks": limit, window = 10, 60
    elif path == "/api/ai/chat": limit, window = 20, 60
    elif request.method in {"POST", "PATCH", "PUT", "DELETE"}: limit, window = 300, 60
    else: return None
    client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    bucket = int(time.time()) // window
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        key = f"cyber:request-rate:{client_ip}:{path}:{bucket}"
        count = client.incr(key)
        if count == 1: client.expire(key, window + 2)
        if count > limit:
            return JSONResponse(status_code=429, headers={"Retry-After": str(window)},
                content={"detail": "Request rate limit exceeded; retry later"})
    except Exception:
        return JSONResponse(status_code=503, content={"detail": "Rate limiter is unavailable"})
    return None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id", "")
        if not request_id or len(request_id) > 64 or not all(c.isalnum() or c in "-_" for c in request_id):
            request_id = uuid4().hex
        request.state.request_id = request_id
        rate_response = _apply_rate_limit(request)
        bearer_ingestion = (request.url.path == "/api/events/ingest" and
            request.headers.get("authorization", "").lower().startswith("bearer "))
        if rate_response:
            response = rate_response
        elif request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"} and not bearer_ingestion:
            try:
                check_csrf(request)
            except Exception as error:
                response = JSONResponse(status_code=403, content={"detail": str(getattr(error, "detail", "Request rejected"))})
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request_id
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        _access_log.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO", "service": "api", "event": "http_request", "request_id": request_id,
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "client_ip": request.headers.get("x-real-ip") or (request.client.host if request.client else None),
            "user_id": getattr(request.state, "user_id", None),
            "organization_id": getattr(request.state, "organization_id", None)}, separators=(",", ":")))
        return response


@asynccontextmanager
async def lifespan(_app):
    if settings.environment == "production" and (len(settings.jwt_secret) < 32 or settings.jwt_secret == "change-this-development-secret-before-deployment"):
        raise RuntimeError("JWT_SECRET must be a unique random secret of at least 32 characters in production")
    if settings.environment == "development":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="CyberShield OS API", version="0.1.0",
              description="Organization-scoped security posture and authorized asset assessment API.", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[settings.app_url], allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"])
api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(dashboard.router)
api.include_router(assets.router)
api.include_router(findings_risks.router)
api.include_router(incidents_events.router)
api.include_router(reports.router)
api.include_router(analyst.router)
api.include_router(search.router)
api.include_router(team.router)
api.include_router(api_keys.router)
api.include_router(events_soc.router)
api.include_router(cases.router)
api.include_router(realtime.router)
api.include_router(analytics.router)
api.include_router(threat_intel.router)
api.include_router(evidence.router)
api.include_router(webhooks.router)
api.include_router(retention.router)
api.include_router(notifications.router)
api.include_router(ops.router)
app.include_router(api)


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})


@app.get("/ready", tags=["system"])
def ready():
    checks = {"database": False, "redis": False, "worker": False}
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception: pass
    try:
        import redis
        checks["redis"] = bool(redis.Redis.from_url(settings.redis_url,
            socket_connect_timeout=1, socket_timeout=1).ping())
    except Exception: pass
    try:
        from services.worker.celery_app import celery_app
        checks["worker"] = bool(celery_app.control.inspect(timeout=0.7).ping())
    except Exception: pass
    healthy = all(checks.values())
    return JSONResponse(status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "degraded", "checks": checks})
