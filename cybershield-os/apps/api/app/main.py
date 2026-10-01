from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy import text
from app.config import settings
from app.db import Base, engine
from app.routes import analyst, assets, auth, dashboard, findings_risks, incidents_events, reports, search, team
from app.security import check_csrf


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                check_csrf(request)
            except Exception as error:
                return JSONResponse(status_code=403, content={"detail": str(getattr(error, "detail", "Request rejected"))})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
                   allow_headers=["Content-Type", "X-CSRF-Token"])
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
app.include_router(api)


@app.get("/api/health", tags=["system"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})
