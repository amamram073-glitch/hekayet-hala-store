from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.dependencies import audit
from app.models import Membership, Organization, User, UserSession
from app.schemas import LoginInput, RegisterInput, StrictInput
from app.security import Principal, get_principal, hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])
_attempts: dict[str, list[float]] = {}

class ChangePasswordInput(StrictInput):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


def _throttle(request: Request):
    now = datetime.now().timestamp()
    key = request.client.host if request.client else "unknown"
    recent = [stamp for stamp in _attempts.get(key, []) if now - stamp < 600]
    if len(recent) >= 10:
        raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again later.")
    recent.append(now)
    _attempts[key] = recent


def _start_session(response: Response, request: Request, db: Session, user: User, org_id, role: str):
    session_id = str(uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    db.add(UserSession(id=session_id, user_id=user.id, organization_id=org_id, expires_at=expires,
                       ip_address=request.client.host if request.client else None,
                       user_agent=request.headers.get("user-agent", "")[:300]))
    token = issue_token(user.id, org_id, session_id)
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/", "max_age": 28800}
    response.set_cookie("cyber_session", token, **common)
    response.set_cookie("csrf_token", str(uuid4()), httponly=False, secure=settings.cookie_secure,
                        samesite="lax", path="/", max_age=28800)
    return {"user": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
            "organization": {"id": str(org_id)}, "role": role}


@router.post("/register", status_code=201)
def register(data: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)):
    _throttle(request)
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, full_name=data.full_name.strip(), password_hash=hash_password(data.password))
    organization = Organization(name=data.organization_name.strip())
    db.add_all([user, organization])
    db.flush()
    membership = Membership(user_id=user.id, organization_id=organization.id, role="ORGANIZATION_OWNER")
    db.add(membership)
    result = _start_session(response, request, db, user, organization.id, membership.role)
    db.add(__import__("app.models", fromlist=["AuditLog"]).AuditLog(
        organization_id=organization.id, actor_id=user.id, action="USER_CREATED", resource="organization",
        resource_id=str(organization.id), ip_address=request.client.host if request.client else None,
        metadata_json={"email": email}))
    db.commit()
    result["organization"]["name"] = organization.name
    return result


@router.post("/login")
def login(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    _throttle(request)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    # Same response for unknown user and incorrect password.
    if not user or not verify_password(data.password, user.password_hash) or not user.active:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.status == "ACTIVE").order_by(Membership.created_at))
    if not membership:
        raise HTTPException(status_code=403, detail="No active organization membership")
    result = _start_session(response, request, db, user, membership.organization_id, membership.role)
    audit(db, Principal(user, membership.organization_id, membership.role, None), request,
          "LOGIN", "session", metadata={"session_login": True})
    db.commit()
    result["organization"]["id"] = str(membership.organization_id)
    return result


@router.post("/logout")
def logout(response: Response, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.session.revoked_at = datetime.now(timezone.utc)
    audit(db, principal, request, "LOGOUT", "session", principal.session.id)
    db.commit()
    response.delete_cookie("cyber_session", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    org = db.get(Organization, principal.organization_id)
    return {"user": {"id": str(principal.user.id), "email": principal.user.email,
                     "full_name": principal.user.full_name},
            "organization": {"id": str(principal.organization_id), "name": org.name if org else ""},
            "role": principal.role}


@router.get("/sessions")
def sessions(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserSession).where(UserSession.user_id == principal.user.id,
                                                 UserSession.revoked_at.is_(None))).all()
    return [{"id": r.id, "current": r.id == principal.session.id, "ip_address": r.ip_address,
             "user_agent": r.user_agent, "created_at": r.created_at, "expires_at": r.expires_at} for r in rows]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    target = db.scalar(select(UserSession).where(UserSession.id == session_id, UserSession.user_id == principal.user.id))
    if not target:
        raise HTTPException(status_code=404, detail="Session not found")
    target.revoked_at = datetime.now(timezone.utc)
    audit(db, principal, request, "SESSION_REVOKED", "session", target.id)
    db.commit()
    return Response(status_code=204)


@router.post("/change-password")
def change_password(data: ChangePasswordInput, request: Request, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    if not verify_password(data.current_password, principal.user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    principal.user.password_hash = hash_password(data.new_password)
    others = db.scalars(select(UserSession).where(UserSession.user_id == principal.user.id,
        UserSession.id != principal.session.id, UserSession.revoked_at.is_(None))).all()
    for item in others:
        item.revoked_at = datetime.now(timezone.utc)
    audit(db, principal, request, "PASSWORD_CHANGED", "user", str(principal.user.id),
          {"revoked_other_sessions": len(others)})
    db.commit()
    return {"ok": True, "revoked_other_sessions": len(others)}
