from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, manager
from app.models import Asset, Finding, Risk, Scan, SecurityEvent
from app.schemas import AssetCreate, AssetUpdate, AuthorizationInput
from app.security import Principal, get_principal
from app.services.scoring import persist_if_changed

router = APIRouter(tags=["assets and scans"])


def _asset_out(a: Asset):
    return {"id": str(a.id), "name": a.name, "type": a.type, "hostname": a.hostname,
            "environment": a.environment, "owner": a.owner, "status": a.status,
            "authorization_status": a.authorization_status, "authorized_at": a.authorized_at,
            "last_checked_at": a.last_checked_at, "created_at": a.created_at}


@router.get("/assets")
def list_assets(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Asset).where(Asset.organization_id == principal.organization_id)
                      .order_by(Asset.created_at.desc())).all()
    return [_asset_out(row) for row in rows]


@router.post("/assets", status_code=201)
def create_asset(data: AssetCreate, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    duplicate = db.scalar(select(Asset).where(Asset.organization_id == principal.organization_id,
                                               Asset.hostname == data.hostname))
    if duplicate:
        raise HTTPException(status_code=409, detail="This hostname is already registered in your organization")
    asset = Asset(organization_id=principal.organization_id, **data.model_dump())
    db.add(asset)
    db.flush()
    audit(db, principal, request, "ASSET_CREATED", "asset", str(asset.id), {"hostname": asset.hostname})
    db.commit()
    db.refresh(asset)
    return _asset_out(asset)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_out(asset)


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: str, data: AssetUpdate, request: Request,
                 principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items(): setattr(asset, field, value)
    audit(db, principal, request, "ASSET_UPDATED", "asset", str(asset.id), {"changed_fields": sorted(changes)})
    db.commit(); db.refresh(asset)
    return _asset_out(asset)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    audit(db, principal, request, "ASSET_DELETED", "asset", str(asset.id), {"hostname": asset.hostname})
    db.execute(update(Risk).where(Risk.asset_id == asset.id, Risk.organization_id == principal.organization_id).values(asset_id=None))
    db.execute(delete(Finding).where(Finding.asset_id == asset.id, Finding.organization_id == principal.organization_id))
    db.execute(delete(Scan).where(Scan.asset_id == asset.id, Scan.organization_id == principal.organization_id))
    db.delete(asset)
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return Response(status_code=204)


@router.post("/assets/{asset_id}/authorize")
def authorize_asset(asset_id: str, data: AuthorizationInput, request: Request,
                   principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    if not data.confirmed:
        raise HTTPException(status_code=400, detail="Explicit authorization confirmation is required")
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    asset.authorization_status = "AUTHORIZED"
    asset.authorization_statement = data.statement.strip()
    asset.authorized_by, asset.authorized_at = principal.user.id, datetime.now(timezone.utc)
    db.add(SecurityEvent(organization_id=principal.organization_id, event_type="ASSET_AUTHORIZED", severity="INFO",
                         message=f"Authorization recorded for {asset.hostname}", metadata_json={"asset_id": str(asset.id)}))
    audit(db, principal, request, "ASSET_AUTHORIZED", "asset", str(asset.id))
    persist_if_changed(db, principal.organization_id)
    db.commit()
    db.refresh(asset)
    return _asset_out(asset)


@router.post("/assets/{asset_id}/revoke")
def revoke_asset(asset_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    asset.authorization_status, asset.authorized_at, asset.authorized_by = "REVOKED", None, None
    audit(db, principal, request, "ASSET_AUTHORIZATION_REVOKED", "asset", str(asset.id))
    persist_if_changed(db, principal.organization_id)
    db.commit()
    return _asset_out(asset)


@router.post("/assets/{asset_id}/scans", status_code=202)
def start_scan(asset_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: aid = UUID(asset_id)
    except ValueError: raise HTTPException(status_code=404, detail="Asset not found")
    asset = db.scalar(select(Asset).where(Asset.id == aid, Asset.organization_id == principal.organization_id))
    if not asset: raise HTTPException(status_code=404, detail="Asset not found")
    if asset.authorization_status != "AUTHORIZED" or asset.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Only active assets with explicit authorization may be scanned")
    scan = Scan(organization_id=principal.organization_id, asset_id=asset.id, status="QUEUED")
    db.add(scan)
    db.flush()
    audit(db, principal, request, "SCAN_STARTED", "scan", str(scan.id), {"asset_id": str(asset.id)})
    db.commit()
    try:
        from services.worker.tasks import scan_asset
        scan_asset.delay(str(scan.id))
    except Exception as error:
        scan.status, scan.error, scan.completed_at = "FAILED", "Background queue unavailable", datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail="Background scan queue is unavailable; start Redis and the Celery worker") from error
    return {"id": str(scan.id), "asset_id": str(asset.id), "status": scan.status, "progress": 0}


@router.get("/scans")
def list_scans(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Scan).where(Scan.organization_id == principal.organization_id)
                      .order_by(Scan.created_at.desc()).limit(100)).all()
    return [{"id": str(s.id), "asset_id": str(s.asset_id), "status": s.status, "progress": s.progress,
             "error": s.error, "results": s.results, "created_at": s.created_at,
             "started_at": s.started_at, "completed_at": s.completed_at} for s in rows]


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try: sid = UUID(scan_id)
    except ValueError: raise HTTPException(status_code=404, detail="Scan not found")
    scan = db.scalar(select(Scan).where(Scan.id == sid, Scan.organization_id == principal.organization_id))
    if not scan: raise HTTPException(status_code=404, detail="Scan not found")
    return {"id": str(scan.id), "asset_id": str(scan.asset_id), "status": scan.status,
            "progress": scan.progress, "error": scan.error, "results": scan.results,
            "created_at": scan.created_at, "started_at": scan.started_at, "completed_at": scan.completed_at}


@router.post("/scans/{scan_id}/stop")
def stop_scan(scan_id: str, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    try: sid = UUID(scan_id)
    except ValueError: raise HTTPException(status_code=404, detail="Scan not found")
    scan = db.scalar(select(Scan).where(Scan.id == sid, Scan.organization_id == principal.organization_id))
    if not scan: raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status != "QUEUED":
        raise HTTPException(status_code=409, detail="Only a queued scan can be stopped")
    scan.status, scan.completed_at = "CANCELLED", datetime.now(timezone.utc)
    audit(db, principal, request, "SCAN_CANCELLED", "scan", str(scan.id))
    db.commit()
    return {"id": str(scan.id), "status": scan.status}
