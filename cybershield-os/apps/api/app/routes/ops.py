import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine, get_db
from app.dependencies import manager
from app.security import Principal

router = APIRouter(prefix="/system", tags=["internal system health"])


@router.get("/health")
def system_health(principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    checks = {}

    def measure(name, callback):
        started = time.perf_counter()
        try:
            detail = callback()
            checks[name] = {"status": "PASS", "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "detail": detail}
        except Exception as error:
            checks[name] = {"status": "FAIL", "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": error.__class__.__name__}

    measure("api", lambda: "request handled")
    def database():
        db.execute(text("SELECT 1"))
        return "connected"
    measure("database", database)
    def redis_check():
        import redis
        return "connected" if redis.Redis.from_url(settings.redis_url,
            socket_connect_timeout=1, socket_timeout=1).ping() else "unavailable"
    measure("redis", redis_check)
    def worker_check():
        from services.worker.celery_app import celery_app
        workers = celery_app.control.inspect(timeout=1).ping() or {}
        if not workers: raise RuntimeError("No worker heartbeat")
        return {"workers": len(workers)}
    measure("worker", worker_check)
    def websocket_bus():
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return "Pub/Sub broker reachable"
    measure("websocket", websocket_bus)
    statuses = {name: item["status"] for name, item in checks.items()}
    return {"status": "PASS" if all(value == "PASS" for value in statuses.values()) else "DEGRADED",
        "checks": checks, "last_check": datetime.now(timezone.utc).isoformat()}
