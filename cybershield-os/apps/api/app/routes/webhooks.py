from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, manager
from app.models import ThreatWebhook, WebhookDelivery
from app.schemas import WebhookCreate
from app.security import Principal
from app.services.webhooks import ALLOWED_WEBHOOK_EVENTS, encrypt_secret, resolve_public_target

router = APIRouter(prefix="/webhooks", tags=["signed outbound webhooks"])


def _uuid(value: str):
    try: return UUID(value)
    except ValueError: raise HTTPException(status_code=404, detail="Webhook not found")


@router.get("")
def list_webhooks(principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    rows = db.scalars(select(ThreatWebhook).where(ThreatWebhook.organization_id == principal.organization_id)
        .order_by(ThreatWebhook.created_at.desc()).limit(100)).all()
    return [{"id": str(x.id), "url": x.url, "event_types": x.event_types,
        "active": x.active, "created_at": x.created_at} for x in rows]


@router.post("", status_code=201)
def create_webhook(data: WebhookCreate, request: Request,
                   principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    unknown = set(data.event_types) - (ALLOWED_WEBHOOK_EVENTS | {"*"})
    if unknown: raise HTTPException(status_code=422, detail="Unsupported webhook event type")
    if len(set(data.event_types)) != len(data.event_types):
        raise HTTPException(status_code=422, detail="Duplicate webhook event type")
    try:
        parsed, host, _ = resolve_public_target(data.url.strip())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    normalized_url = parsed.geturl()
    row = ThreatWebhook(organization_id=principal.organization_id,
        created_by_id=principal.user.id, url=normalized_url,
        secret_ciphertext=encrypt_secret(data.secret), event_types=data.event_types,
        active=True)
    db.add(row)
    db.flush()
    audit(db, principal, request, "WEBHOOK_CREATED", "webhook", str(row.id),
        {"host": host, "event_types": data.event_types})
    db.commit()
    return {"id": str(row.id), "url": row.url, "event_types": row.event_types,
        "active": row.active, "secret_saved": True, "secret_returned": False,
        "created_at": row.created_at}


@router.get("/{webhook_id}/deliveries")
def list_deliveries(webhook_id: str, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    wid = _uuid(webhook_id)
    hook = db.scalar(select(ThreatWebhook).where(ThreatWebhook.id == wid,
        ThreatWebhook.organization_id == principal.organization_id))
    if not hook: raise HTTPException(status_code=404, detail="Webhook not found")
    rows = db.scalars(select(WebhookDelivery).where(WebhookDelivery.webhook_id == wid,
        WebhookDelivery.organization_id == principal.organization_id).order_by(WebhookDelivery.created_at.desc()).limit(200)).all()
    return [{"id": str(x.id), "event_type": x.event_type, "status": x.status,
        "attempts": x.attempts, "last_error": x.last_error,
        "next_attempt_at": x.next_attempt_at, "created_at": x.created_at} for x in rows]


@router.delete("/{webhook_id}", status_code=204)
def disable_webhook(webhook_id: str, request: Request,
                    principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    wid = _uuid(webhook_id)
    row = db.scalar(select(ThreatWebhook).where(ThreatWebhook.id == wid,
        ThreatWebhook.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Webhook not found")
    row.active = False
    audit(db, principal, request, "WEBHOOK_DISABLED", "webhook", str(row.id))
    db.commit()
    return None
