import json
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import Membership, User, UserSession
import jwt

router = APIRouter(tags=["real-time SOC"])


@router.websocket("/ws/events")
async def event_stream(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") != settings.app_url.rstrip("/"):
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get("cyber_session")
    if not token:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id, organization_id = UUID(claims["sub"]), UUID(claims["org"])
        session = db.get(UserSession, claims.get("sid"))
        user = db.get(User, user_id)
        membership = db.scalar(select(Membership).where(Membership.user_id == user_id,
            Membership.organization_id == organization_id, Membership.status == "ACTIVE"))
        expires_at = session.expires_at if session else None
        if expires_at and expires_at.tzinfo is None: expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (not session or session.revoked_at or not expires_at or expires_at <= datetime.now(timezone.utc)
            or not user or not user.active or not membership
            or session.organization_id != membership.organization_id or session.user_id != user.id):
            await websocket.close(code=4401)
            return
        org_id = str(membership.organization_id)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        await websocket.close(code=4401)
        return
    finally:
        db.close()
    try:
        import redis.asyncio as redis
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=30,
                                decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"cybershield:org:{org_id}:events")
        await websocket.accept()
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    try:
                        await websocket.send_text(json.dumps(json.loads(message["data"]), default=str))
                    except (WebSocketDisconnect, RuntimeError):
                        break
        finally:
            await pubsub.unsubscribe(f"cybershield:org:{org_id}:events")
            await pubsub.aclose()
            await client.aclose()
    except Exception:
        # Never expose broker, credentials or stack details over the socket.
        try: await websocket.close(code=1013, reason="Real-time service temporarily unavailable")
        except Exception: pass
