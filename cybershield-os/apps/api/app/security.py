from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import Membership, User, UserSession

_passwords = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _passwords.verify(encoded, password)
    except (VerifyMismatchError, VerificationError):
        return False


def issue_token(user_id: UUID, organization_id: UUID, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "org": str(organization_id), "sid": session_id,
                       "iat": now, "exp": now + timedelta(hours=8)}, settings.jwt_secret, algorithm="HS256")


@dataclass
class Principal:
    user: User
    organization_id: UUID
    role: str
    session: UserSession


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = request.cookies.get("cyber_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id, org_id, session_id = UUID(claims["sub"]), UUID(claims["org"]), claims["sid"]
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    session = db.get(UserSession, session_id)
    user = db.get(User, user_id)
    membership = db.scalar(select(Membership).where(
        Membership.user_id == user_id,
        Membership.organization_id == org_id,
        Membership.status == "ACTIVE",
    ))
    expires_at = session.expires_at if session else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not session or session.revoked_at or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session has expired or was revoked")
    if not user or not user.active or not membership or session.user_id != user_id or session.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access is not permitted")
    return Principal(user=user, organization_id=org_id, role=membership.role, session=session)


def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=403, detail="Your organization role cannot perform this action")
        return principal
    return dependency


def check_csrf(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"} or "cyber_session" not in request.cookies:
        return
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("x-csrf-token")
    origin = request.headers.get("origin")
    if not cookie or not header or cookie != header:
        raise HTTPException(status_code=403, detail="CSRF token validation failed")
    if origin and origin.rstrip("/") != settings.app_url.rstrip("/"):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")
