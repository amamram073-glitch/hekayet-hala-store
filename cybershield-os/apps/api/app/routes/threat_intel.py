import ipaddress
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import analyst, audit, manager
from app.models import ThreatIndicator
from app.schemas import IndicatorCreate
from app.security import Principal

router = APIRouter(tags=["threat intelligence"])


def normalize_indicator(kind: str, value: str) -> str:
    raw = value.strip()
    if kind == "IP":
        try: return str(ipaddress.ip_address(raw))
        except ValueError: raise HTTPException(status_code=422, detail="Indicator must be a valid IP address")
    if kind == "DOMAIN":
        if "://" in raw or "/" in raw or "@" in raw:
            raise HTTPException(status_code=422, detail="Use a bare hostname for a DOMAIN indicator")
        try: normalized = raw.rstrip(".").lower().encode("idna").decode("ascii")
        except UnicodeError: raise HTTPException(status_code=422, detail="Invalid domain indicator")
        if len(normalized) > 253 or not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*", normalized):
            raise HTTPException(status_code=422, detail="Invalid domain indicator")
        return normalized
    if kind == "URL":
        from urllib.parse import urlsplit
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(status_code=422, detail="URL indicators must be absolute HTTP(S) URLs without embedded credentials")
        return raw.lower().rstrip("/")
    if kind == "HASH":
        normalized = raw.lower()
        if not re.fullmatch(r"(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})", normalized):
            raise HTTPException(status_code=422, detail="Hash must be a valid MD5, SHA-1, SHA-256, or SHA-512 value")
        return normalized
    if kind == "EMAIL":
        if len(raw) > 320 or raw.count("@") != 1:
            raise HTTPException(status_code=422, detail="Invalid email indicator")
        return raw.casefold()
    raise HTTPException(status_code=422, detail="Unsupported indicator type")


def _view(row):
    return {"id": str(row.id), "type": row.type, "value": row.value,
        "confidence": row.confidence, "source": row.source, "tags": row.tags or [],
        "description": row.description, "first_seen": row.first_seen_at,
        "last_seen": row.last_seen_at, "created_at": row.created_at}


@router.get("/indicators")
def list_indicators(q: str | None = None, kind: str | None = None,
                    principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    stmt = select(ThreatIndicator).where(ThreatIndicator.organization_id == principal.organization_id)
    if q: stmt = stmt.where(ThreatIndicator.value.ilike(f"%{q[:120]}%"))
    if kind:
        if kind not in {"IP", "DOMAIN", "URL", "HASH", "EMAIL"}: raise HTTPException(status_code=422, detail="Invalid indicator type")
        stmt = stmt.where(ThreatIndicator.type == kind)
    rows = db.scalars(stmt.order_by(ThreatIndicator.last_seen_at.desc()).limit(200)).all()
    return [_view(row) for row in rows]


@router.post("/indicators", status_code=201)
def create_indicator(data: IndicatorCreate, request: Request,
                     principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    normalized = normalize_indicator(data.type, data.value)
    row = ThreatIndicator(organization_id=principal.organization_id, type=data.type,
        value=data.value.strip(), normalized_value=normalized, confidence=data.confidence,
        source=data.source.strip(), tags=[tag.strip()[:60] for tag in data.tags if tag.strip()],
        description=data.description)
    db.add(row)
    db.flush()
    audit(db, principal, request, "THREAT_INDICATOR_CREATED", "indicator", str(row.id), {"type": row.type, "source": row.source})
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="This indicator already exists in the organization")
    return _view(row)


@router.delete("/indicators/{indicator_id}", status_code=204)
def delete_indicator(indicator_id: str, request: Request,
                     principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: iid = __import__("uuid").UUID(indicator_id)
    except ValueError: raise HTTPException(status_code=404, detail="Indicator not found")
    row = db.scalar(select(ThreatIndicator).where(ThreatIndicator.id == iid,
        ThreatIndicator.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Indicator not found")
    audit(db, principal, request, "THREAT_INDICATOR_DELETED", "indicator", str(row.id), {"type": row.type})
    db.delete(row)
    db.commit()
