from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Asset, Finding, Scan, SecurityEvent
from app.services.scanner import safe_scan, findings_from_result
from app.services.scoring import persist_if_changed
from services.worker.celery_app import celery_app


@celery_app.task(name="cybershield.scan_asset", bind=True, max_retries=0)
def scan_asset(self, scan_id: str):
    db = SessionLocal()
    try:
        try:
            scan_uuid = UUID(scan_id)
        except (ValueError, TypeError):
            return {"status": "cancelled"}
        scan = db.get(Scan, scan_uuid)
        if not scan or scan.status in {"CANCELLED", "COMPLETED"}:
            return {"status": "cancelled"}
        asset = db.scalar(select(Asset).where(Asset.id == scan.asset_id,
            Asset.organization_id == scan.organization_id,
            Asset.authorization_status == "AUTHORIZED", Asset.status == "ACTIVE"))
        if not asset:
            scan.status, scan.error, scan.completed_at = "FAILED", "Asset authorization is not active", datetime.now(timezone.utc)
            db.commit()
            return {"status": "failed", "reason": "authorization_required"}
        scan.status, scan.progress, scan.started_at = "RUNNING", 10, datetime.now(timezone.utc)
        db.commit()
        result = safe_scan(asset.hostname)
        scan = db.get(Scan, scan_uuid)
        if not scan or scan.status == "CANCELLED":
            return {"status": "cancelled"}
        scan.results, scan.progress = result, 90
        finding_rows = findings_from_result(asset.id, asset.organization_id, scan.id, result)
        for data in finding_rows:
            db.add(Finding(**data))
        asset.last_checked_at = datetime.now(timezone.utc)
        scan.status, scan.progress, scan.completed_at = "COMPLETED", 100, datetime.now(timezone.utc)
        db.add(SecurityEvent(organization_id=asset.organization_id, event_type="SCAN_COMPLETED", severity="INFO",
                             message=f"Safe assessment completed for {asset.hostname}", metadata_json={"scan_id": scan_id}))
        critical = sum(item["severity"] == "CRITICAL" for item in finding_rows)
        high = sum(item["severity"] == "HIGH" for item in finding_rows)
        if critical or high:
            db.add(SecurityEvent(organization_id=asset.organization_id, event_type="FINDINGS_DETECTED",
                severity="CRITICAL" if critical else "HIGH", message=f"Assessment detected {critical} critical and {high} high findings on {asset.hostname}",
                metadata_json={"scan_id": scan_id, "critical": critical, "high": high}))
        persist_if_changed(db, asset.organization_id)
        db.commit()
        return {"status": "completed", "scan_id": scan_id}
    except Exception as error:
        db.rollback()
        scan = db.get(Scan, scan_uuid)
        if scan:
            scan.status, scan.error, scan.completed_at = "FAILED", error.__class__.__name__, datetime.now(timezone.utc)
            db.commit()
        return {"status": "failed", "reason": error.__class__.__name__}
    finally:
        db.close()
