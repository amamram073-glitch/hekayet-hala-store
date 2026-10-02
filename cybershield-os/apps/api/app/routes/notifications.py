from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit
from app.models import Notification
from app.security import Principal, get_principal

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _view(row):
    return {"id": str(row.id), "type": row.notification_type, "title": row.title,
        "message": row.message, "resource_type": row.resource_type,
        "resource_id": row.resource_id, "read_at": row.read_at, "created_at": row.created_at}


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0, le=10000), principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    query = select(Notification).where(Notification.organization_id == principal.organization_id,
        Notification.user_id == principal.user.id)
    if unread_only: query = query.where(Notification.read_at.is_(None))
    rows = db.scalars(query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)).all()
    return [_view(row) for row in rows]


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, request: Request, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    try: nid = UUID(notification_id)
    except ValueError: raise HTTPException(status_code=404, detail="Notification not found")
    row = db.scalar(select(Notification).where(Notification.id == nid,
        Notification.organization_id == principal.organization_id, Notification.user_id == principal.user.id))
    if not row: raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        audit(db, principal, request, "NOTIFICATION_READ", "notification", str(row.id))
        db.commit()
    return _view(row)
