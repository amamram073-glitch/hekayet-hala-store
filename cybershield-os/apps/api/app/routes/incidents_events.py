from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import analyst, audit, manager
from app.models import AuditLog, Incident, SecurityEvent
from app.schemas import IncidentCreate, IncidentUpdate
from app.security import Principal, get_principal
from app.services.scoring import persist_if_changed

router = APIRouter(tags=["incidents, events and audit"])


@router.get("/incidents")
def list_incidents(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident).where(Incident.organization_id == principal.organization_id).order_by(Incident.detected_at.desc())).all()
    return [{"id": str(x.id), "title": x.title, "description": x.description, "severity": x.severity,
             "status": x.status, "assigned_to": x.assigned_to, "detected_at": x.detected_at,
             "resolved_at": x.resolved_at, "notes": x.notes or []} for x in rows]


@router.post("/incidents", status_code=201)
def create_incident(data: IncidentCreate, request: Request, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    incident = Incident(organization_id=principal.organization_id, **data.model_dump())
    db.add(incident)
    db.flush()
    db.add(SecurityEvent(organization_id=principal.organization_id, event_type="INCIDENT_CREATED",
                         severity=data.severity, message=data.title, metadata_json={"incident_id": str(incident.id)}))
    audit(db, principal, request, "INCIDENT_CREATED", "incident", str(incident.id))
    from app.services.webhooks import create_delivery_rows
    create_delivery_rows(db, principal.organization_id, "INCIDENT_CREATED", {
        "type": "INCIDENT_CREATED", "organization_id": str(principal.organization_id),
        "incident_id": str(incident.id), "title": incident.title,
        "severity": incident.severity, "status": incident.status,
        "occurred_at": incident.detected_at,
    })
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return {"id": str(incident.id), "title": incident.title, "status": incident.status}


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: str, data: IncidentUpdate, request: Request,
                    principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    try: iid = UUID(incident_id)
    except ValueError: raise HTTPException(status_code=404, detail="Incident not found")
    row = db.scalar(select(Incident).where(Incident.id == iid, Incident.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Incident not found")
    row.status = data.status
    row.resolved_at = datetime.now(timezone.utc) if data.status in ("RESOLVED", "CLOSED") else None
    audit(db, principal, request, "INCIDENT_STATUS_CHANGED", "incident", str(row.id), {"status": row.status})
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.post("/incidents/{incident_id}/notes")
def add_incident_note(incident_id: str, payload: dict, request: Request,
                      principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    text = str(payload.get("note", "")).strip()
    if not text or len(text) > 5000: raise HTTPException(status_code=422, detail="Note must be between 1 and 5000 characters")
    try: iid = UUID(incident_id)
    except ValueError: raise HTTPException(status_code=404, detail="Incident not found")
    row = db.scalar(select(Incident).where(Incident.id == iid, Incident.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Incident not found")
    row.notes = list(row.notes or []) + [{"note": text, "author": principal.user.full_name, "at": datetime.now(timezone.utc).isoformat()}]
    audit(db, principal, request, "INCIDENT_NOTE_ADDED", "incident", str(row.id))
    db.commit()
    return {"id": str(row.id), "notes": row.notes}


@router.get("/events")
def list_events(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=10000),
                severity: str | None = Query(None, pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$"),
                source_type: str | None = Query(None, pattern="^(APPLICATION|WEB_SERVER|AUTHENTICATION|ENDPOINT|CLOUD|FIREWALL|DNS|API)$"),
                q: str | None = Query(None, min_length=1, max_length=100),
                since: datetime | None = None, until: datetime | None = None,
                principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    query = select(SecurityEvent).where(SecurityEvent.organization_id == principal.organization_id)
    if severity: query = query.where(SecurityEvent.severity == severity)
    if source_type: query = query.where(SecurityEvent.source_type == source_type)
    if q:
        from sqlalchemy import or_
        pattern = f"%{q}%"
        query = query.where(or_(SecurityEvent.event_type.ilike(pattern), SecurityEvent.source.ilike(pattern),
            SecurityEvent.username.ilike(pattern), SecurityEvent.hostname.ilike(pattern), SecurityEvent.message.ilike(pattern)))
    if since: query = query.where(SecurityEvent.event_timestamp >= since)
    if until: query = query.where(SecurityEvent.event_timestamp <= until)
    rows = db.scalars(query.order_by(SecurityEvent.event_timestamp.desc()).offset(offset).limit(limit)).all()
    return [{"id": str(x.id), "event_type": x.event_type, "severity": x.severity, "source": x.source,
             "message": x.message, "metadata": x.metadata_json, "processing_status": x.processing_status,
             "hostname": x.hostname, "username": x.username, "asset_id": str(x.asset_id) if x.asset_id else None,
             "event_timestamp": x.event_timestamp, "created_at": x.created_at} for x in rows]


@router.get("/audit-logs")
def list_audit_logs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=10000),
                    action: str | None = Query(None, min_length=1, max_length=64),
                    request_id: str | None = Query(None, min_length=1, max_length=64),
                    principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    query = select(AuditLog).where(AuditLog.organization_id == principal.organization_id)
    if action: query = query.where(AuditLog.action == action)
    if request_id: query = query.where(AuditLog.request_id == request_id)
    rows = db.scalars(query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)).all()
    return [{"id": str(x.id), "actor_id": str(x.actor_id) if x.actor_id else None,
             "action": x.action, "resource": x.resource, "resource_id": x.resource_id,
             "ip_address": x.ip_address, "user_agent": x.user_agent, "request_id": x.request_id,
             "before_state": x.before_state, "after_state": x.after_state,
             "metadata": x.metadata_json, "created_at": x.created_at} for x in rows]
