import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.dependencies import audit, manager
from app.models import Invitation, Membership, Organization, User
from app.schemas import StrictInput
from app.security import Principal, get_principal, hash_password
from app.routes.auth import _start_session

router = APIRouter(prefix="/team", tags=["organization team"])
ALLOWED_ROLES = {"SECURITY_ADMIN", "SECURITY_ANALYST", "IT_ADMIN", "EMPLOYEE", "VIEWER"}

class InviteInput(StrictInput):
    email: EmailStr
    role: str = Field(pattern="^(SECURITY_ADMIN|SECURITY_ANALYST|IT_ADMIN|EMPLOYEE|VIEWER)$")

class AcceptInput(StrictInput):
    token: str = Field(min_length=32, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)

class MemberUpdate(StrictInput):
    role: str | None = Field(default=None, pattern="^(ORGANIZATION_OWNER|SECURITY_ADMIN|SECURITY_ANALYST|IT_ADMIN|EMPLOYEE|VIEWER)$")
    status: str | None = Field(default=None, pattern="^(ACTIVE|SUSPENDED)$")

@router.get("/members")
def members(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, Membership.user_id == User.id).where(
        Membership.organization_id == principal.organization_id).order_by(Membership.created_at)).all()
    return [{"user_id": str(m.user_id), "full_name": u.full_name, "email": u.email,
             "role": m.role, "status": m.status, "created_at": m.created_at} for m, u in rows]

@router.post("/invitations", status_code=201)
def invite(data: InviteInput, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    email = data.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing and db.scalar(select(Membership).where(Membership.user_id == existing.id,
            Membership.organization_id == principal.organization_id)):
        raise HTTPException(status_code=409, detail="User is already a member")
    token = secrets.token_urlsafe(36)
    invitation = Invitation(organization_id=principal.organization_id, email=email, role=data.role,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc)+timedelta(days=7))
    db.add(invitation); db.flush()
    audit(db, principal, request, "USER_INVITED", "invitation", str(invitation.id), {"email": email, "role": data.role})
    db.commit()
    return {"id": str(invitation.id), "email": email, "role": data.role,
            "expires_at": invitation.expires_at, "invite_url": f"{settings.app_url.rstrip('/')}/join?token={token}"}

@router.post("/accept-invitation", status_code=201)
def accept(data: AcceptInput, request: Request, response: Response, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash, Invitation.accepted_at.is_(None)))
    expiry = invitation.expires_at if invitation else None
    if expiry and expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
    if not invitation or not expiry or expiry <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    if db.scalar(select(User).where(User.email == invitation.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists; ask an administrator to manage membership")
    user = User(email=invitation.email, full_name=data.full_name.strip(), password_hash=hash_password(data.password))
    db.add(user); db.flush()
    member = Membership(organization_id=invitation.organization_id, user_id=user.id, role=invitation.role, status="ACTIVE")
    db.add(member); invitation.accepted_at = datetime.now(timezone.utc)
    result = _start_session(response, request, db, user, invitation.organization_id, invitation.role)
    db.commit()
    result["organization"] = {"id": str(invitation.organization_id)}
    return result

@router.patch("/members/{user_id}")
def update_member(user_id: str, data: MemberUpdate, request: Request,
                  principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: uid = UUID(user_id)
    except ValueError: raise HTTPException(status_code=404, detail="Member not found")
    member = db.scalar(select(Membership).where(Membership.organization_id == principal.organization_id,
                                                Membership.user_id == uid))
    if not member: raise HTTPException(status_code=404, detail="Member not found")
    if data.role == "ORGANIZATION_OWNER" and principal.role != "ORGANIZATION_OWNER":
        raise HTTPException(status_code=403, detail="Only an organization owner can grant owner access")
    if uid == principal.user.id and (data.status == "SUSPENDED" or data.role not in (None, "ORGANIZATION_OWNER")):
        raise HTTPException(status_code=400, detail="You cannot suspend or demote your own active session")
    if member.role == "ORGANIZATION_OWNER" and data.role and data.role != "ORGANIZATION_OWNER":
        owners = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.organization_id == principal.organization_id, Membership.role == "ORGANIZATION_OWNER", Membership.status == "ACTIVE")) or 0
        if owners <= 1: raise HTTPException(status_code=409, detail="The organization must retain at least one active owner")
    if data.role: member.role = data.role
    if data.status: member.status = data.status
    audit(db, principal, request, "MEMBER_UPDATED", "membership", str(member.id),
          {"role": member.role, "status": member.status})
    db.commit()
    return {"user_id": str(member.user_id), "role": member.role, "status": member.status}

@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: uid = UUID(user_id)
    except ValueError: raise HTTPException(status_code=404, detail="Member not found")
    member = db.scalar(select(Membership).where(Membership.organization_id == principal.organization_id,
                                                Membership.user_id == uid))
    if not member: raise HTTPException(status_code=404, detail="Member not found")
    if uid == principal.user.id:
        raise HTTPException(status_code=400, detail="Transfer ownership or use another owner account before removing yourself")
    if member.role == "ORGANIZATION_OWNER":
        owners = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.organization_id == principal.organization_id, Membership.role == "ORGANIZATION_OWNER", Membership.status == "ACTIVE")) or 0
        if owners <= 1: raise HTTPException(status_code=409, detail="The last active owner cannot be removed")
    audit(db, principal, request, "MEMBER_REMOVED", "membership", str(member.id))
    db.delete(member); db.commit()
    return Response(status_code=204)
