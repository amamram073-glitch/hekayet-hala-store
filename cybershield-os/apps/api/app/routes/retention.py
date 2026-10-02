from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, manager
from app.models import DataRetentionPolicy
from app.schemas import RetentionPolicyUpdate
from app.security import Principal

router = APIRouter(prefix="/retention-policy", tags=["event retention"])


def _view(row):
    if not row:
        return {"event_retention_days": 90, "enabled": False, "updated_at": None,
            "note": "Retention is disabled by default. Enabling it purges only expired, processed events not linked to alerts or investigations; audit logs are never purged by this job."}
    return {"event_retention_days": row.event_retention_days, "enabled": row.enabled,
        "updated_at": row.updated_at, "note": "Expired events linked to alerts or investigations are preserved; audit logs are not subject to this policy."}


@router.get("")
def get_retention_policy(principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    row = db.scalar(select(DataRetentionPolicy).where(
        DataRetentionPolicy.organization_id == principal.organization_id))
    return _view(row)


@router.put("")
def put_retention_policy(data: RetentionPolicyUpdate, request: Request,
                         principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    row = db.scalar(select(DataRetentionPolicy).where(
        DataRetentionPolicy.organization_id == principal.organization_id))
    before = _view(row)
    if row is None:
        row = DataRetentionPolicy(organization_id=principal.organization_id,
            updated_by_id=principal.user.id, **data.model_dump())
        db.add(row)
    else:
        row.event_retention_days = data.event_retention_days
        row.enabled = data.enabled
        row.updated_by_id = principal.user.id
        row.updated_at = datetime.now(timezone.utc)
    audit(db, principal, request, "RETENTION_POLICY_UPDATED", "retention_policy",
        str(principal.organization_id), {"before_state": before,
            "after_state": data.model_dump()})
    db.commit()
    return _view(row)
