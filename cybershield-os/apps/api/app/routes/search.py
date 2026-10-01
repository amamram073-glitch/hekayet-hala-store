from sqlalchemy import or_, select
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Asset, Finding, Incident, Report, User
from app.security import Principal, get_principal

router = APIRouter(tags=["search"])


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=100), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    pattern = f"%{q}%"
    assets = db.scalars(select(Asset).where(Asset.organization_id == principal.organization_id,
        or_(Asset.name.ilike(pattern), Asset.hostname.ilike(pattern))).limit(20)).all()
    findings = db.scalars(select(Finding).where(Finding.organization_id == principal.organization_id,
        or_(Finding.title.ilike(pattern), Finding.description.ilike(pattern))).limit(20)).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == principal.organization_id,
        or_(Incident.title.ilike(pattern), Incident.description.ilike(pattern))).limit(20)).all()
    reports = db.scalars(select(Report).where(Report.organization_id == principal.organization_id,
        Report.title.ilike(pattern)).limit(20)).all()
    return {"assets": [{"id": str(x.id), "name": x.name, "hostname": x.hostname} for x in assets],
            "findings": [{"id": str(x.id), "title": x.title, "severity": x.severity} for x in findings],
            "incidents": [{"id": str(x.id), "title": x.title, "status": x.status} for x in incidents],
            "reports": [{"id": str(x.id), "title": x.title} for x in reports]}
