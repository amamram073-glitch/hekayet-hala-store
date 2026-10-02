import ipaddress
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import analyst, audit, manager
from app.models import (Alert, AlertEventLink, AlertNote, ApiKey, Asset, DetectionRule,
    Incident, Investigation, SecurityEvent, ThreatIndicator, now_utc)
from app.schemas import (AlertNoteCreate, AlertUpdate, DetectionRuleCreate,
    DetectionRuleUpdate, EventIngestInput)
from app.security import Principal

router = APIRouter(tags=["SOC events, alerts and detection"])


def _uuid(value: str, label: str):
    try: return UUID(value)
    except (ValueError, TypeError): raise HTTPException(status_code=404, detail=f"{label} not found")


def _alert_view(row: Alert):
    return {"id": str(row.id), "title": row.title, "description": row.description,
        "reason": row.reason, "severity": row.severity, "status": row.status,
        "source": row.source, "asset_id": str(row.asset_id) if row.asset_id else None,
        "username": row.username, "risk_score": row.risk_score,
        "recommendation": row.recommendation, "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at, "created_at": row.created_at,
        "resolved_at": row.resolved_at,
        "detection_rule_id": str(row.detection_rule_id) if row.detection_rule_id else None}


def _event_view(event: SecurityEvent):
    return {"id": str(event.id), "organization_id": str(event.organization_id),
        "timestamp": event.event_timestamp, "source": event.source,
        "source_type": event.source_type, "event_type": event.event_type,
        "severity": event.severity, "hostname": event.hostname,
        "ip_address": event.ip_address, "username": event.username,
        "asset_id": str(event.asset_id) if event.asset_id else None,
        "message": event.message, "metadata": event.metadata_json or {},
        "processing_status": event.processing_status, "created_at": event.created_at}


def _api_key_for_request(request: Request, db: Session) -> ApiKey:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="An organization API key is required")
    import hashlib
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = db.scalar(select(ApiKey).where(ApiKey.token_hash == digest, ApiKey.revoked_at.is_(None)).with_for_update())
    if not row:
        raise HTTPException(status_code=401, detail="API key is invalid or revoked")
    if "EVENT_INGEST" not in (row.permissions or []):
        raise HTTPException(status_code=403, detail="API key does not permit event ingestion")
    now = datetime.now(timezone.utc)
    started = row.window_started_at
    if started.tzinfo is None: started = started.replace(tzinfo=timezone.utc)
    if now - started >= timedelta(minutes=1):
        row.window_started_at, row.window_count = now, 1
    else:
        row.window_count += 1
    if row.window_count > row.per_minute_limit:
        db.commit()
        raise HTTPException(status_code=429, detail="Event ingestion rate limit exceeded")
    row.last_used_at = now
    db.commit()
    return row


@router.post("/events/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_event(data: EventIngestInput, request: Request, db: Session = Depends(get_db)):
    api_key = _api_key_for_request(request, db)
    asset_id = None
    if data.asset_id:
        asset_uuid = _uuid(data.asset_id, "Asset")
        asset = db.scalar(select(Asset).where(Asset.id == asset_uuid,
            Asset.organization_id == api_key.organization_id, Asset.status == "ACTIVE"))
        if not asset: raise HTTPException(status_code=404, detail="Asset not found")
        asset_id = asset.id
    hostname = data.hostname.strip().rstrip(".").lower() if data.hostname else None
    if hostname:
        try: hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError: raise HTTPException(status_code=422, detail="Hostname is invalid")
    source_ip = data.ip_address
    if source_ip:
        try: source_ip = str(ipaddress.ip_address(source_ip.strip()))
        except ValueError: raise HTTPException(status_code=422, detail="IP address is invalid")
    event_time = data.timestamp or datetime.now(timezone.utc)
    if event_time.tzinfo is None: event_time = event_time.replace(tzinfo=timezone.utc)
    if event_time > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Event timestamp cannot be more than five minutes in the future")
    row = SecurityEvent(organization_id=api_key.organization_id,
        event_type=data.event_type.strip().upper(), severity=data.severity.upper(),
        source=data.source.strip(), source_type=data.source_type.upper(),
        event_timestamp=event_time, hostname=hostname, ip_address=source_ip,
        username=data.username.strip() if data.username else None, asset_id=asset_id,
        message=data.message.strip(), metadata_json=data.metadata,
        processing_status="PENDING")
    db.add(row)
    db.commit()
    # Commit a queue state before dispatch to avoid racing a fast worker's PROCESSED update.
    row.processing_status = "QUEUED"
    db.commit()
    # If Redis is briefly unavailable, the durable event remains visibly PENDING and can be
    # retried by operations rather than silently discarded.
    try:
        from services.worker.tasks import process_security_event
        process_security_event.delay(str(row.id))
    except Exception:
        db.rollback()
        row = db.get(SecurityEvent, row.id)
        if row:
            row.processing_status = "PENDING"
            db.commit()
    return {"id": str(row.id), "organization_id": str(api_key.organization_id),
            "timestamp": row.event_timestamp, "processing_status": row.processing_status}


@router.get("/detection-rules")
def list_detection_rules(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    rows = db.scalars(select(DetectionRule).where(DetectionRule.organization_id == principal.organization_id)
        .order_by(DetectionRule.created_at.desc()).limit(200)).all()
    return [{"id": str(r.id), "name": r.name, "description": r.description, "severity": r.severity,
        "enabled": r.enabled, "conditions": r.conditions, "created_at": r.created_at} for r in rows]


@router.post("/detection-rules", status_code=201)
def create_detection_rule(data: DetectionRuleCreate, request: Request,
                         principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    values = data.model_dump()
    conditions = {"conditions": [item.model_dump() for item in data.conditions],
                  "match_count": data.match_count, "window_minutes": data.window_minutes}
    row = DetectionRule(organization_id=principal.organization_id, name=values["name"],
        description=values["description"], severity=values["severity"], enabled=values["enabled"], conditions=conditions)
    db.add(row)
    try:
        db.flush()
        audit(db, principal, request, "DETECTION_RULE_CREATED", "detection_rule", str(row.id), {"name": row.name})
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="A rule with this name already exists")
    return {"id": str(row.id), "name": row.name, "enabled": row.enabled, "conditions": row.conditions}


@router.patch("/detection-rules/{rule_id}")
def update_detection_rule(rule_id: str, data: DetectionRuleUpdate, request: Request,
                          principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    rid = _uuid(rule_id, "Detection rule")
    row = db.scalar(select(DetectionRule).where(DetectionRule.id == rid,
        DetectionRule.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Detection rule not found")
    values = data.model_dump(exclude_unset=True)
    conditions = dict(row.conditions or {})
    for field in ("conditions", "match_count", "window_minutes"):
        if field in values:
            value = values.pop(field)
            if field == "conditions": conditions[field] = [x.model_dump() for x in value]
            else: conditions[field] = value
    for field, value in values.items(): setattr(row, field, value)
    if conditions != (row.conditions or {}): row.conditions = conditions
    audit(db, principal, request, "DETECTION_RULE_UPDATED", "detection_rule", str(row.id), {"fields": list(data.model_fields_set)})
    db.commit()
    return {"id": str(row.id), "name": row.name, "enabled": row.enabled,
        "severity": row.severity, "conditions": row.conditions}


@router.get("/alerts")
def list_alerts(q: str | None = Query(default=None, max_length=160),
    severity: str | None = Query(default=None, pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$"),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(NEW|ACKNOWLEDGED|INVESTIGATING|RESOLVED|FALSE_POSITIVE)$"),
    source: str | None = Query(default=None, max_length=120), asset_id: str | None = None,
    since: datetime | None = None, until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0, le=100000),
    principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    stmt = select(Alert).where(Alert.organization_id == principal.organization_id)
    if severity: stmt = stmt.where(Alert.severity == severity)
    if status_filter: stmt = stmt.where(Alert.status == status_filter)
    if source: stmt = stmt.where(Alert.source.ilike(f"%{source}%"))
    if asset_id: stmt = stmt.where(Alert.asset_id == _uuid(asset_id, "Asset"))
    if since: stmt = stmt.where(Alert.created_at >= since)
    if until: stmt = stmt.where(Alert.created_at <= until)
    if q: stmt = stmt.where((Alert.title.ilike(f"%{q}%")) | (Alert.reason.ilike(f"%{q}%")) | (Alert.username.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [_alert_view(row) for row in rows], "limit": limit, "offset": offset, "total": total}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    aid = _uuid(alert_id, "Alert")
    row = db.scalar(select(Alert).where(Alert.id == aid, Alert.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Alert not found")
    links = db.scalars(select(AlertEventLink).where(AlertEventLink.organization_id == principal.organization_id,
        AlertEventLink.alert_id == row.id).order_by(AlertEventLink.created_at.asc()).limit(200)).all()
    event_ids = [link.event_id for link in links]
    events = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == principal.organization_id,
        SecurityEvent.id.in_(event_ids)).order_by(SecurityEvent.event_timestamp.asc()).limit(200)).all() if event_ids else []
    notes = db.scalars(select(AlertNote).where(AlertNote.organization_id == principal.organization_id,
        AlertNote.alert_id == row.id).order_by(AlertNote.created_at.asc()).limit(200)).all()
    asset = db.scalar(select(Asset).where(Asset.id == row.asset_id,
        Asset.organization_id == principal.organization_id)) if row.asset_id else None
    return {**_alert_view(row), "asset": {"id": str(asset.id), "name": asset.name, "hostname": asset.hostname} if asset else None,
        "events": [_event_view(event) for event in events],
        "notes": [{"id": str(n.id), "content": n.content, "created_at": n.created_at,
                   "user_id": str(n.user_id) if n.user_id else None} for n in notes],
        "timeline": [{"type": "event", "at": e.event_timestamp, "label": e.event_type, "event_id": str(e.id)} for e in events]}


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: str, data: AlertUpdate, request: Request,
                 principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    aid = _uuid(alert_id, "Alert")
    row = db.scalar(select(Alert).where(Alert.id == aid, Alert.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Alert not found")
    before = row.status
    row.status = data.status
    now = datetime.now(timezone.utc)
    if data.status == "ACKNOWLEDGED" and not row.acknowledged_at: row.acknowledged_at = now
    row.resolved_at = now if data.status in {"RESOLVED", "FALSE_POSITIVE"} else None
    audit(db, principal, request, "ALERT_STATUS_CHANGED", "alert", str(row.id), {"before": before, "after": row.status})
    db.commit()
    return _alert_view(row)


@router.post("/alerts/{alert_id}/notes", status_code=201)
def add_alert_note(alert_id: str, data: AlertNoteCreate, request: Request,
                   principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    aid = _uuid(alert_id, "Alert")
    row = db.scalar(select(Alert).where(Alert.id == aid, Alert.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Alert not found")
    note = AlertNote(organization_id=principal.organization_id, alert_id=row.id,
        user_id=principal.user.id, content=data.content)
    db.add(note)
    audit(db, principal, request, "ALERT_NOTE_ADDED", "alert", str(row.id))
    db.commit()
    return {"id": str(note.id), "content": note.content, "created_at": note.created_at}


@router.get("/soc/overview")
def soc_overview(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    org = principal.organization_id
    now = datetime.now(timezone.utc)
    minute_ago, day_ago = now - timedelta(minutes=1), now - timedelta(days=1)
    active_incidents = db.scalar(select(func.count(Incident.id)).where(Incident.organization_id == org,
        Incident.status.notin_(["RESOLVED", "CLOSED"]))) or 0
    open_investigations = db.scalar(select(func.count(Investigation.id)).where(Investigation.organization_id == org,
        Investigation.status.notin_(["RESOLVED", "CLOSED"]))) or 0
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == org,
        Alert.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    critical = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == org,
        Alert.severity == "CRITICAL", Alert.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    epm = db.scalar(select(func.count(SecurityEvent.id)).where(SecurityEvent.organization_id == org,
        SecurityEvent.event_timestamp >= minute_ago)) or 0
    monitored = db.scalar(select(func.count(Asset.id)).where(Asset.organization_id == org,
        Asset.status == "ACTIVE", Asset.authorization_status == "AUTHORIZED")) or 0
    rule_count = db.scalar(select(func.count(DetectionRule.id)).where(DetectionRule.organization_id == org,
        DetectionRule.enabled.is_(True))) or 0
    event_count = db.scalar(select(func.count(SecurityEvent.id)).where(SecurityEvent.organization_id == org,
        SecurityEvent.event_timestamp >= day_ago)) or 0
    recent_events = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == org)
        .order_by(SecurityEvent.event_timestamp.desc()).limit(12)).all()
    recent_alerts = db.scalars(select(Alert).where(Alert.organization_id == org,
        Alert.created_at >= day_ago).order_by(Alert.created_at.desc()).limit(20)).all()
    resolved = db.scalars(select(Alert).where(Alert.organization_id == org,
        Alert.status == "RESOLVED", Alert.resolved_at.is_not(None)).limit(500)).all()
    threats_24h = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == org,
        Alert.created_at >= day_ago)) or 0
    processing_backlog = db.scalar(select(func.count(SecurityEvent.id)).where(
        SecurityEvent.organization_id == org, SecurityEvent.processing_status.in_(["PENDING", "QUEUED", "PROCESSING"]))) or 0
    failed_events = db.scalar(select(func.count(SecurityEvent.id)).where(
        SecurityEvent.organization_id == org, SecurityEvent.processing_status == "FAILED",
        SecurityEvent.event_timestamp >= day_ago)) or 0
    mttr = sum(max(0, (a.resolved_at - a.created_at).total_seconds()) for a in resolved) / len(resolved) / 60 if resolved else None
    alert_ids = [a.id for a in recent_alerts]
    links = db.scalars(select(AlertEventLink).where(AlertEventLink.organization_id == org,
        AlertEventLink.alert_id.in_(alert_ids)).limit(1000)).all() if alert_ids else []
    by_id = {e.id: e for e in recent_events}
    mtte_values = []
    if links:
        evs = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == org,
            SecurityEvent.id.in_([x.event_id for x in links])).limit(1000)).all()
        by_id.update({e.id: e for e in evs})
        for alert in recent_alerts:
            first = [by_id[x.event_id].event_timestamp for x in links if x.alert_id == alert.id and x.event_id in by_id]
            if first: mtte_values.append(max(0, (alert.created_at - min(first)).total_seconds()) / 60)
    mttd = sum(mtte_values) / len(mtte_values) if mtte_values else None
    return {"overall_status": "ATTENTION" if critical or active_incidents else "MONITORING",
        "active_incidents": active_incidents, "critical_alerts": critical, "open_alerts": open_alerts,
        "events_per_minute": epm, "events_24h": event_count, "threat_activity_24h": threats_24h,
        "event_processing_backlog": processing_backlog, "event_processing_failures_24h": failed_events,
        "open_investigations": open_investigations, "assets_under_monitoring": monitored,
        "enabled_detection_rules": rule_count, "mttd_minutes": round(mttd, 2) if mttd is not None else None,
        "mttr_minutes": round(mttr, 2) if mttr is not None else None,
        "recent_events": [_event_view(e) for e in recent_events],
        "recent_alerts": [_alert_view(a) for a in recent_alerts[:8]]}
