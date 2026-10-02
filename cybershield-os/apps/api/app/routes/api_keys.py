import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, manager
from app.models import ApiKey
from app.schemas import ApiKeyCreate
from app.security import Principal

router = APIRouter(prefix="/api-keys", tags=["organization API keys"])


def _mint_key():
    raw = "cso_" + secrets.token_urlsafe(32)
    return raw, raw[:12], hashlib.sha256(raw.encode()).hexdigest()


def _safe_view(row: ApiKey):
    return {"id": str(row.id), "name": row.name, "key_prefix": row.key_prefix,
            "permissions": row.permissions or [], "last_used_at": row.last_used_at,
            "revoked_at": row.revoked_at, "created_at": row.created_at,
            "per_minute_limit": row.per_minute_limit}


@router.get("")
def list_api_keys(principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApiKey).where(ApiKey.organization_id == principal.organization_id)
        .order_by(ApiKey.created_at.desc()).limit(200)).all()
    return [_safe_view(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(data: ApiKeyCreate, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    raw, prefix, digest = _mint_key()
    row = ApiKey(organization_id=principal.organization_id, created_by=principal.user.id,
        name=data.name, key_prefix=prefix, token_hash=digest, permissions=data.permissions,
        per_minute_limit=120, window_started_at=datetime.now(timezone.utc), window_count=0)
    db.add(row)
    db.flush()
    audit(db, principal, request, "API_KEY_CREATED", "api_key", str(row.id), {"name": row.name, "permissions": row.permissions})
    db.commit()
    return {**_safe_view(row), "api_key": raw, "warning": "Copy this key now. It cannot be displayed again."}


@router.post("/{key_id}/rotate", status_code=status.HTTP_201_CREATED)
def rotate_api_key(key_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: key_uuid = UUID(key_id)
    except ValueError: raise HTTPException(status_code=404, detail="API key not found")
    old = db.scalar(select(ApiKey).where(ApiKey.id == key_uuid, ApiKey.organization_id == principal.organization_id))
    if not old: raise HTTPException(status_code=404, detail="API key not found")
    old.revoked_at = datetime.now(timezone.utc)
    raw, prefix, digest = _mint_key()
    row = ApiKey(organization_id=principal.organization_id, created_by=principal.user.id,
        name=old.name, key_prefix=prefix, token_hash=digest, permissions=list(old.permissions or []),
        per_minute_limit=old.per_minute_limit, window_started_at=datetime.now(timezone.utc), window_count=0)
    db.add(row)
    db.flush()
    audit(db, principal, request, "API_KEY_ROTATED", "api_key", str(row.id), {"revoked_key_id": str(old.id)})
    db.commit()
    return {**_safe_view(row), "api_key": raw, "warning": "Copy this replacement now; the previous key has been revoked."}


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: key_uuid = UUID(key_id)
    except ValueError: raise HTTPException(status_code=404, detail="API key not found")
    row = db.scalar(select(ApiKey).where(ApiKey.id == key_uuid, ApiKey.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="API key not found")
    if not row.revoked_at:
        row.revoked_at = datetime.now(timezone.utc)
        audit(db, principal, request, "API_KEY_REVOKED", "api_key", str(row.id), {"name": row.name})
        db.commit()
    return None
