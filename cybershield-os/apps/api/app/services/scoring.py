from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Asset, Finding, Incident, Risk, ScoreSnapshot

SEVERITY_PENALTY = {"CRITICAL": 15, "HIGH": 8, "MEDIUM": 3, "LOW": 1, "INFO": 0}


def calculate_score(db: Session, organization_id) -> int:
    db.flush()
    findings = db.scalars(select(Finding).where(Finding.organization_id == organization_id,
                                                 Finding.status.in_(["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"]))).all()
    risks = db.scalars(select(Risk).where(Risk.organization_id == organization_id, Risk.status == "OPEN")).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == organization_id,
                                                  Incident.status.in_(["OPEN", "INVESTIGATING", "CONTAINED"]))).all()
    assets = db.scalars(select(Asset).where(Asset.organization_id == organization_id,
                                            Asset.status == "ACTIVE")).all()
    penalty = sum(SEVERITY_PENALTY.get(item.severity, 0) for item in findings)
    penalty += min(20, sum(max(1, item.risk_score // 4) for item in risks))
    penalty += min(20, sum(5 if item.severity in ("CRITICAL", "HIGH") else 2 for item in incidents))
    if assets:
        penalty += min(10, round(10 * sum(a.authorization_status != "AUTHORIZED" for a in assets) / len(assets)))
    return max(0, min(100, 100 - penalty))


def score_label(score: int) -> str:
    if score >= 90: return "Excellent"
    if score >= 75: return "Good"
    if score >= 60: return "Needs Attention"
    if score >= 40: return "High Risk"
    return "Critical Risk"


def persist_score(db: Session, organization_id) -> int:
    score = calculate_score(db, organization_id)
    db.add(ScoreSnapshot(organization_id=organization_id, score=score))
    return score


def persist_if_changed(db: Session, organization_id) -> int:
    score = calculate_score(db, organization_id)
    latest = db.scalar(select(ScoreSnapshot).where(ScoreSnapshot.organization_id == organization_id)
                       .order_by(ScoreSnapshot.created_at.desc()).limit(1))
    if latest is None or latest.score != score:
        db.add(ScoreSnapshot(organization_id=organization_id, score=score))
    return score
