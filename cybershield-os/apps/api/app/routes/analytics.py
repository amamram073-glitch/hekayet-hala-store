from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, analyst, manager
from app.models import (Alert, AlertEventLink, Asset, AuditLog, Finding, Incident,
    Investigation, InvestigationLink, Risk, SecurityEvent, SecurityPostureSnapshot,
    SecurityCase, now_utc)
from app.security import Principal
from app.services.scoring import calculate_score

router = APIRouter(tags=["SOC metrics and security posture"])


@router.get("/soc/posture")
def posture_history(period: str = Query(default="30d", pattern="^(today|7d|30d|90d|1y)$"),
                   principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    starts = {"today": now - timedelta(days=1), "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30), "90d": now - timedelta(days=90), "1y": now - timedelta(days=365)}
    rows = db.scalars(select(SecurityPostureSnapshot).where(
        SecurityPostureSnapshot.organization_id == principal.organization_id,
        SecurityPostureSnapshot.created_at >= starts[period]).order_by(SecurityPostureSnapshot.created_at.asc()).limit(1000)).all()
    return {"period": period, "items": [{"security_score": r.security_score,
        "risk_score": r.risk_score, "critical_findings": r.critical_findings,
        "open_incidents": r.open_incidents, "compliance_score": r.compliance_score,
        "created_at": r.created_at} for r in rows]}


@router.post("/soc/posture/snapshot", status_code=201)
def save_posture_snapshot(request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    org = principal.organization_id
    score = calculate_score(db, org)
    critical = db.scalar(select(func.count(Finding.id)).where(Finding.organization_id == org,
        Finding.severity == "CRITICAL", Finding.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    incidents = db.scalar(select(func.count(Incident.id)).where(Incident.organization_id == org,
        Incident.status.notin_(["RESOLVED", "CLOSED"]))) or 0
    risks = db.scalar(select(func.avg(Risk.risk_score)).where(Risk.organization_id == org,
        Risk.status != "CLOSED")) or 0
    # Compliance is unknown until a framework assessment exists; zero here is an explicit
    # unavailable baseline, not an assertion that the organization has no controls.
    row = SecurityPostureSnapshot(organization_id=org, security_score=score,
        risk_score=int(risks), critical_findings=critical, open_incidents=incidents,
        compliance_score=0)
    db.add(row)
    audit(db, principal, request, "POSTURE_SNAPSHOT_CREATED", "security_posture", str(row.id),
        {"compliance_score_status": "not_assessed"})
    db.commit()
    return {"id": str(row.id), "security_score": row.security_score,
        "risk_score": row.risk_score, "critical_findings": row.critical_findings,
        "open_incidents": row.open_incidents, "compliance_score": row.compliance_score,
        "compliance_status": "NOT_ASSESSED", "created_at": row.created_at}


@router.get("/soc/risk-graph")
def risk_graph(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    org = principal.organization_id
    nodes, edges = [], []
    nodes.append({"id": f"org:{org}", "type": "organization", "label": "Organization"})
    assets = db.scalars(select(Asset).where(Asset.organization_id == org).limit(500)).all()
    findings = db.scalars(select(Finding).where(Finding.organization_id == org).limit(1000)).all()
    alerts = db.scalars(select(Alert).where(Alert.organization_id == org).limit(1000)).all()
    events = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == org).order_by(SecurityEvent.event_timestamp.desc()).limit(1000)).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == org).limit(500)).all()
    investigations = db.scalars(select(Investigation).where(Investigation.organization_id == org).limit(500)).all()
    cases = db.scalars(select(SecurityCase).where(SecurityCase.organization_id == org).limit(500)).all()
    for row in assets:
        nodes.append({"id": f"asset:{row.id}", "type": "asset", "label": row.name})
        edges.append({"source": f"org:{org}", "target": f"asset:{row.id}", "type": "owns"})
    for row in findings:
        nodes.append({"id": f"finding:{row.id}", "type": "finding", "label": row.title})
        edges.append({"source": f"asset:{row.asset_id}", "target": f"finding:{row.id}", "type": "has_finding"})
    for row in alerts:
        nodes.append({"id": f"alert:{row.id}", "type": "alert", "label": row.title})
        if row.asset_id: edges.append({"source": f"asset:{row.asset_id}", "target": f"alert:{row.id}", "type": "raised_alert"})
    links = db.scalars(select(AlertEventLink).where(AlertEventLink.organization_id == org).limit(2000)).all()
    event_by_id = {row.id: row for row in events}
    for row in events:
        nodes.append({"id": f"event:{row.id}", "type": "event", "label": row.event_type})
        if row.asset_id: edges.append({"source": f"asset:{row.asset_id}", "target": f"event:{row.id}", "type": "generated_event"})
    for link in links:
        if link.event_id in event_by_id:
            edges.append({"source": f"event:{link.event_id}", "target": f"alert:{link.alert_id}", "type": "triggered_alert"})
    for row in incidents:
        nodes.append({"id": f"incident:{row.id}", "type": "incident", "label": row.title})
    for row in investigations:
        nodes.append({"id": f"investigation:{row.id}", "type": "investigation", "label": row.title})
    for link in db.scalars(select(InvestigationLink).where(InvestigationLink.organization_id == org).limit(2000)).all():
        target = f"{link.resource_type.lower()}:{link.resource_id}" if link.resource_type != "NOTE" else None
        if target and any(n["id"] == target for n in nodes):
            edges.append({"source": f"investigation:{link.investigation_id}", "target": target, "type": "contains"})
    for row in cases:
        nodes.append({"id": f"case:{row.id}", "type": "case", "label": row.case_number + " · " + row.title})
        if row.incident_id:
            edges.append({"source": f"case:{row.id}", "target": f"incident:{row.incident_id}", "type": "tracks"})
    return {"nodes": nodes, "edges": edges, "truncated": len(nodes) >= 4000}


@router.get("/security-center")
def security_center(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    org = principal.organization_id
    critical = db.scalar(select(func.count(Finding.id)).where(Finding.organization_id == org,
        Finding.severity == "CRITICAL", Finding.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    pending_assets = db.scalar(select(func.count(Asset.id)).where(Asset.organization_id == org,
        Asset.authorization_status == "PENDING")) or 0
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == org,
        Alert.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    checks = [
        {"area": "application", "name": "API health", "status": "PASS", "evidence": "API process answered the authenticated request."},
        {"area": "authentication", "name": "Session-bound organization", "status": "PASS", "evidence": "Current request has an active organization membership."},
        {"area": "organization", "name": "Tenant scope", "status": "PASS", "evidence": "Data queries are scoped to the current organization."},
        {"area": "asset", "name": "Pending authorization", "status": "WARNING" if pending_assets else "PASS", "evidence": f"{pending_assets} asset(s) are pending authorization and cannot be scanned."},
        {"area": "application", "name": "Open alerts", "status": "FAIL" if critical else "WARNING" if open_alerts else "PASS", "evidence": f"{critical} open critical; {open_alerts} open total."},
        {"area": "cloud", "name": "Cloud provider posture", "status": "WARNING", "evidence": "No external cloud-provider integration has been configured."},
        {"area": "compliance", "name": "Compliance controls", "status": "WARNING", "evidence": "No framework assessment is configured; compliance is not assessed."},
    ]
    return {"checks": checks, "generated_at": now_utc()}


@router.get("/soc/metrics")
def soc_metrics(period: str = Query(default="30d", pattern="^(24h|7d|30d|90d)$"),
               principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    starts = {"24h": now - timedelta(hours=24), "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30), "90d": now - timedelta(days=90)}
    alerts = db.scalars(select(Alert).where(Alert.organization_id == principal.organization_id,
        Alert.created_at >= starts[period]).order_by(Alert.created_at.asc()).limit(5000)).all()
    mttd_samples, mttr_samples = [], []
    linked_alerts = db.execute(select(Alert.created_at, Alert.resolved_at, Alert.status,
        func.min(SecurityEvent.event_timestamp)).join(AlertEventLink,
        AlertEventLink.alert_id == Alert.id).join(SecurityEvent,
        SecurityEvent.id == AlertEventLink.event_id).where(
        Alert.organization_id == principal.organization_id,
        AlertEventLink.organization_id == principal.organization_id,
        SecurityEvent.organization_id == principal.organization_id,
        Alert.created_at >= starts[period]).group_by(Alert.id, Alert.created_at,
        Alert.resolved_at, Alert.status).limit(5000)).all()
    for created, resolved, status, first_event in linked_alerts:
        if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
        if first_event:
            if first_event.tzinfo is None: first_event = first_event.replace(tzinfo=timezone.utc)
            seconds = (created - first_event).total_seconds()
            if 0 <= seconds <= 365 * 24 * 3600: mttd_samples.append(seconds)
        if resolved and status == "RESOLVED":
            if resolved.tzinfo is None: resolved = resolved.replace(tzinfo=timezone.utc)
            seconds = (resolved - created).total_seconds()
            if 0 <= seconds <= 365 * 24 * 3600: mttr_samples.append(seconds)
    hourly = []
    for hour in range(24):
        start = (now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23-hour))
        end = start + timedelta(hours=1)
        count = db.scalar(select(func.count(SecurityEvent.id)).where(
            SecurityEvent.organization_id == principal.organization_id,
            SecurityEvent.event_timestamp >= start, SecurityEvent.event_timestamp < end)) or 0
        hourly.append({"hour": start.isoformat(), "events": count})
    severities = {}
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        severities[severity] = sum(1 for row in alerts if row.severity == severity)

    def metric(values):
        if not values: return {"value_seconds": None, "sample_count": 0, "status": "INSUFFICIENT_DATA"}
        return {"value_seconds": round(sum(values) / len(values), 2),
            "sample_count": len(values), "status": "MEASURED"}

    event_count = db.scalar(select(func.count(SecurityEvent.id)).where(
        SecurityEvent.organization_id == principal.organization_id,
        SecurityEvent.event_timestamp >= starts[period])) or 0
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == principal.organization_id,
        Alert.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    resolved_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.organization_id == principal.organization_id,
        Alert.status == "RESOLVED", Alert.resolved_at >= starts[period])) or 0
    false_positives = sum(1 for row in alerts if row.status == "FALSE_POSITIVE")
    false_positive_rate = round(false_positives / len(alerts), 4) if alerts else None
    critical_findings = db.scalar(select(func.count(Finding.id)).where(
        Finding.organization_id == principal.organization_id, Finding.severity == "CRITICAL",
        Finding.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
    remediated = db.scalars(select(Finding).where(Finding.organization_id == principal.organization_id,
        Finding.status == "RESOLVED", Finding.resolved_at.is_not(None),
        Finding.resolved_at >= starts[period]).limit(5000)).all()
    remediation = []
    for finding in remediated:
        start = finding.first_detected_at
        end = finding.resolved_at
        if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        delta = (end - start).total_seconds()
        if 0 <= delta <= 365 * 24 * 3600: remediation.append(delta)
    incident_start = now - timedelta(days=180)
    incident_rows = db.scalars(select(Incident).where(Incident.organization_id == principal.organization_id,
        Incident.detected_at >= incident_start).order_by(Incident.detected_at.asc()).limit(5000)).all()
    incidents_by_month = {}
    for incident in incident_rows:
        month = incident.detected_at.strftime("%Y-%m")
        incidents_by_month[month] = incidents_by_month.get(month, 0) + 1
    posture = db.scalars(select(SecurityPostureSnapshot).where(
        SecurityPostureSnapshot.organization_id == principal.organization_id,
        SecurityPostureSnapshot.created_at >= now - timedelta(days=90))
        .order_by(SecurityPostureSnapshot.created_at.asc()).limit(1000)).all()
    risk_trend = [{"date": x.created_at.isoformat(), "risk_score": x.risk_score,
        "security_score": x.security_score} for x in posture]
    return {"period": period, "mttd": metric(mttd_samples), "mttr": metric(mttr_samples),
        "alerts_by_severity": severities, "events_by_hour": hourly, "event_count": event_count,
        "alert_count": len(alerts), "open_alerts": open_alerts, "resolved_alerts": resolved_alerts,
        "false_positive_rate": false_positive_rate, "critical_findings": critical_findings,
        "average_remediation_time": metric(remediation),
        "incidents_by_month": [{"month": k, "count": v} for k, v in sorted(incidents_by_month.items())],
        "risk_trend": risk_trend, "posture_history_status": "MEASURED" if posture else "INSUFFICIENT_DATA",
        "generated_at": now,
        "note": "MTTD is measured from the earliest linked event timestamp to alert creation; MTTR from alert creation to recorded resolution. Empty cohorts are returned as insufficient data, never estimated."}
