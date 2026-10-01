from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Asset, Finding, Incident, Risk, ScoreSnapshot
from app.security import Principal, get_principal
from app.services.scoring import calculate_score, score_label

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    org = principal.organization_id
    assets = db.scalars(select(Asset).where(Asset.organization_id == org)).all()
    findings = db.scalars(select(Finding).where(Finding.organization_id == org)).all()
    risks = db.scalars(select(Risk).where(Risk.organization_id == org)).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == org)).all()
    score = calculate_score(db, org)
    today = datetime.now(timezone.utc).date()
    recent = db.scalar(select(ScoreSnapshot).where(ScoreSnapshot.organization_id == org)
                        .order_by(ScoreSnapshot.created_at.desc()).limit(1))
    if not recent or (recent.created_at.date() if recent.created_at.tzinfo else recent.created_at.date()) < today:
        db.add(ScoreSnapshot(organization_id=org, score=score))
        db.commit()
    history = db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.organization_id == org)
                         .order_by(ScoreSnapshot.created_at.desc()).limit(30)).all()
    severity = {level: sum(f.severity == level and f.status not in ("RESOLVED", "FALSE_POSITIVE") for f in findings)
                for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")}
    categories = {}
    for finding in findings:
        if finding.status not in ("RESOLVED", "FALSE_POSITIVE"):
            categories[finding.category] = categories.get(finding.category, 0) + 1
    exposure = [{"name": a.name, "authorized": a.authorization_status == "AUTHORIZED",
                 "findings": sum(f.asset_id == a.id and f.status == "OPEN" for f in findings)} for a in assets[:12]]
    return {"security_score": score, "risk_level": score_label(score),
            "critical_findings": severity["CRITICAL"], "high_findings": severity["HIGH"],
            "medium_findings": severity["MEDIUM"], "low_findings": severity["LOW"],
            "assets": len(assets), "vulnerable_assets": len({str(f.asset_id) for f in findings if f.status == "OPEN"}),
            "open_incidents": sum(i.status not in ("RESOLVED", "CLOSED") for i in incidents),
            "open_risks": sum(r.status == "OPEN" for r in risks), "employee_security_score": None,
            "compliance_score": None,
            "score_history": [{"score": x.score, "date": x.created_at.isoformat()} for x in reversed(history)],
            "severity_distribution": severity,
            "findings_by_category": [{"category": k, "count": v} for k, v in sorted(categories.items())],
            "asset_exposure": exposure,
            "events_over_time": [],
            "updated_at": datetime.now(timezone.utc).isoformat()}
