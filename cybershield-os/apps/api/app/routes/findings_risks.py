from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import analyst, audit, manager
from app.models import Asset, Finding, Risk
from app.schemas import FindingUpdate, RiskCreate, RiskUpdate
from app.security import Principal, get_principal
from app.services.scoring import persist_if_changed

router = APIRouter(tags=["findings and risks"])


@router.get("/findings")
def list_findings(severity: str | None = None, status: str | None = None,
                  principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    q = select(Finding).where(Finding.organization_id == principal.organization_id)
    if severity: q = q.where(Finding.severity == severity.upper())
    if status: q = q.where(Finding.status == status.upper())
    rows = db.scalars(q.order_by(Finding.first_detected_at.desc()).limit(500)).all()
    assets = {str(a.id): a.name for a in db.scalars(select(Asset).where(Asset.organization_id == principal.organization_id)).all()}
    return [{"id": str(f.id), "asset_id": str(f.asset_id), "asset_name": assets.get(str(f.asset_id), "Unknown asset"),
             "scan_id": str(f.scan_id) if f.scan_id else None, "title": f.title, "description": f.description,
             "severity": f.severity, "category": f.category, "evidence": f.evidence,
             "remediation": f.remediation, "status": f.status, "cve": f.cve,
             "first_detected_at": f.first_detected_at, "last_detected_at": f.last_detected_at,
             "resolved_at": f.resolved_at} for f in rows]


@router.get("/vulnerabilities")
def list_vulnerabilities(severity: str | None = None, status: str | None = None,
                         principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return list_findings(severity, status, principal, db)


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try: fid = UUID(finding_id)
    except ValueError: raise HTTPException(status_code=404, detail="Finding not found")
    row = db.scalar(select(Finding).where(Finding.id == fid, Finding.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Finding not found")
    asset = db.scalar(select(Asset).where(Asset.id == row.asset_id, Asset.organization_id == principal.organization_id))
    return {"id": str(row.id), "asset_id": str(row.asset_id), "asset_name": asset.name if asset else "Unknown asset",
            "scan_id": str(row.scan_id) if row.scan_id else None, "title": row.title, "description": row.description,
            "severity": row.severity, "category": row.category, "evidence": row.evidence,
            "remediation": row.remediation, "status": row.status, "cve": row.cve,
            "first_detected_at": row.first_detected_at, "last_detected_at": row.last_detected_at,
            "resolved_at": row.resolved_at}


@router.patch("/findings/{finding_id}")
def update_finding(finding_id: str, data: FindingUpdate, request: Request,
                   principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    try: fid = UUID(finding_id)
    except ValueError: raise HTTPException(status_code=404, detail="Finding not found")
    row = db.scalar(select(Finding).where(Finding.id == fid, Finding.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Finding not found")
    row.status = data.status
    row.resolved_at = datetime.now(timezone.utc) if data.status in ("RESOLVED", "FALSE_POSITIVE") else None
    audit(db, principal, request, "FINDING_STATUS_CHANGED", "finding", str(row.id), {"status": row.status})
    score = persist_if_changed(db, principal.organization_id)
    db.commit()
    return {"id": str(row.id), "status": row.status, "security_score": score}


@router.get("/risks")
def list_risks(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Risk).where(Risk.organization_id == principal.organization_id).order_by(Risk.risk_score.desc())).all()
    return [{"id": str(r.id), "asset_id": str(r.asset_id) if r.asset_id else None,
             "title": r.title, "description": r.description, "likelihood": r.likelihood, "impact": r.impact,
             "risk_score": r.risk_score, "owner": r.owner, "treatment": r.treatment,
             "deadline": r.deadline, "status": r.status, "created_at": r.created_at} for r in rows]


@router.post("/risks", status_code=201)
def create_risk(data: RiskCreate, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    asset_id = None
    if data.asset_id:
        try: asset_id = UUID(data.asset_id)
        except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.organization_id == principal.organization_id))
        if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    row = Risk(organization_id=principal.organization_id, asset_id=asset_id,
               **data.model_dump(exclude={"asset_id"}), risk_score=data.likelihood * data.impact)
    db.add(row)
    db.flush()
    audit(db, principal, request, "RISK_CREATED", "risk", str(row.id))
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return {"id": str(row.id), "title": row.title, "risk_score": row.risk_score, "status": row.status}


@router.patch("/risks/{risk_id}")
def update_risk(risk_id: str, data: RiskUpdate, request: Request,
                principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: rid = UUID(risk_id)
    except ValueError: raise HTTPException(status_code=404, detail="Risk not found")
    row = db.scalar(select(Risk).where(Risk.id == rid, Risk.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Risk not found")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items(): setattr(row, field, value)
    audit(db, principal, request, "RISK_UPDATED", "risk", str(row.id), jsonable_encoder(changes))
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return {"id": str(row.id), "status": row.status, "treatment": row.treatment,
            "owner": row.owner, "risk_score": row.risk_score, "deadline": row.deadline}
