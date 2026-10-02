from sqlalchemy import or_, select
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (Alert, Asset, Finding, Incident, Investigation,
    Report, SecurityCase, SecurityEvent, ThreatIndicator)
from app.security import Principal, get_principal

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=100),
          principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    pattern = f"%{q}%"
    org = principal.organization_id
    assets = db.scalars(select(Asset).where(Asset.organization_id == org,
        or_(Asset.name.ilike(pattern), Asset.hostname.ilike(pattern))).limit(20)).all()
    findings = db.scalars(select(Finding).where(Finding.organization_id == org,
        or_(Finding.title.ilike(pattern), Finding.description.ilike(pattern))).limit(20)).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == org,
        or_(Incident.title.ilike(pattern), Incident.description.ilike(pattern))).limit(20)).all()
    reports = db.scalars(select(Report).where(Report.organization_id == org,
        Report.title.ilike(pattern)).limit(20)).all()
    alerts = db.scalars(select(Alert).where(Alert.organization_id == org,
        or_(Alert.title.ilike(pattern), Alert.reason.ilike(pattern), Alert.username.ilike(pattern))).limit(20)).all()
    events = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == org,
        or_(SecurityEvent.event_type.ilike(pattern), SecurityEvent.source.ilike(pattern),
            SecurityEvent.hostname.ilike(pattern), SecurityEvent.username.ilike(pattern),
            SecurityEvent.message.ilike(pattern))).order_by(SecurityEvent.event_timestamp.desc()).limit(20)).all()
    investigations = db.scalars(select(Investigation).where(Investigation.organization_id == org,
        or_(Investigation.title.ilike(pattern), Investigation.description.ilike(pattern))).limit(20)).all()
    cases = db.scalars(select(SecurityCase).where(SecurityCase.organization_id == org,
        or_(SecurityCase.case_number.ilike(pattern), SecurityCase.title.ilike(pattern))).limit(20)).all()
    indicators = db.scalars(select(ThreatIndicator).where(ThreatIndicator.organization_id == org,
        or_(ThreatIndicator.value.ilike(pattern), ThreatIndicator.source.ilike(pattern))).limit(20)).all()
    return {
        "assets": [{"id": str(x.id), "name": x.name, "hostname": x.hostname} for x in assets],
        "findings": [{"id": str(x.id), "title": x.title, "severity": x.severity} for x in findings],
        "incidents": [{"id": str(x.id), "title": x.title, "status": x.status} for x in incidents],
        "reports": [{"id": str(x.id), "title": x.title} for x in reports],
        "alerts": [{"id": str(x.id), "title": x.title, "severity": x.severity, "status": x.status} for x in alerts],
        "events": [{"id": str(x.id), "title": x.event_type, "severity": x.severity,
            "timestamp": x.event_timestamp} for x in events],
        "investigations": [{"id": str(x.id), "title": x.title, "status": x.status} for x in investigations],
        "cases": [{"id": str(x.id), "title": x.title, "case_number": x.case_number, "status": x.status} for x in cases],
        "indicators": [{"id": str(x.id), "title": x.value, "type": x.type} for x in indicators],
    }
