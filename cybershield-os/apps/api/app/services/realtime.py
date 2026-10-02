import json
from app.config import settings


def publish_org_event(organization_id: str, payload: dict) -> bool:
    """Best-effort notification transport; the authoritative event remains in SQL."""
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1,
                                      decode_responses=True)
        client.publish(f"cybershield:org:{organization_id}:events", json.dumps(payload, default=str))
        client.close()
        return True
    except Exception:
        return False
