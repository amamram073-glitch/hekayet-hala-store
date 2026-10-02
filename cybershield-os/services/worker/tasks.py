from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import String, cast, delete, select
from app.db import SessionLocal
from app.models import (AlertEventLink, Asset, AuditLog, DataRetentionPolicy, Finding,
    Incident, Organization, Risk, Scan, SecurityEvent, SecurityPostureSnapshot, WebhookDelivery)
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
        scan_event = SecurityEvent(organization_id=asset.organization_id, event_type="SCAN_COMPLETED", severity="INFO",
            message=f"Safe assessment completed for {asset.hostname}", metadata_json={"scan_id": scan_id})
        db.add(scan_event)
        critical = sum(item["severity"] == "CRITICAL" for item in finding_rows)
        high = sum(item["severity"] == "HIGH" for item in finding_rows)
        if critical or high:
            critical_event = SecurityEvent(organization_id=asset.organization_id, event_type="FINDINGS_DETECTED",
                severity="CRITICAL" if critical else "HIGH", message=f"Assessment detected {critical} critical and {high} high findings on {asset.hostname}",
                metadata_json={"scan_id": scan_id, "critical": critical, "high": high})
            db.add(critical_event)
        db.flush()
        from app.services.webhooks import create_delivery_rows
        create_delivery_rows(db, asset.organization_id, "SCAN_COMPLETED", {
            "type": "SCAN_COMPLETED", "organization_id": str(asset.organization_id),
            "scan_id": scan_id, "asset_id": str(asset.id), "hostname": asset.hostname,
            "status": scan.status, "finding_count": len(finding_rows), "occurred_at": scan.completed_at})
        if critical or high:
            create_delivery_rows(db, asset.organization_id, "HIGH_SEVERITY_EVENT", {
                "type": "HIGH_SEVERITY_EVENT", "organization_id": str(asset.organization_id),
                "scan_id": scan_id, "asset_id": str(asset.id), "hostname": asset.hostname,
                "critical_findings": critical, "high_findings": high, "occurred_at": scan.completed_at})
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


@celery_app.task(name="cybershield.process_security_event", bind=True, max_retries=0)
def process_security_event(self, event_id: str):
    """Process one already-persisted, organization-scoped normalized event."""
    db = SessionLocal()
    try:
        try:
            event_uuid = UUID(event_id)
        except (ValueError, TypeError):
            return {"status": "invalid_event_id"}
        event = db.get(SecurityEvent, event_uuid)
        if not event:
            return {"status": "not_found"}
        if event.processing_status == "PROCESSED":
            return {"status": "already_processed"}
        from app.services.detection import evaluate_event
        from app.services.realtime import publish_org_event
        event.processing_status = "PROCESSING"
        db.flush()
        alerts = evaluate_event(db, event)
        db.commit()
        publish_org_event(str(event.organization_id), {
            "type": "security_event",
            "event": {"id": str(event.id), "event_type": event.event_type,
                "severity": event.severity, "source": event.source,
                "source_type": event.source_type, "message": event.message,
                "timestamp": event.event_timestamp.isoformat()},
            "alerts": [{"id": str(a.id), "title": a.title, "severity": a.severity,
                "status": a.status, "risk_score": a.risk_score} for a in alerts],
        })
        return {"status": "processed", "event_id": event_id, "alerts": len(alerts)}
    except Exception as error:
        db.rollback()
        event = db.get(SecurityEvent, event_uuid) if "event_uuid" in locals() else None
        if event:
            event.processing_status = "PENDING"
            db.commit()
        return {"status": "failed", "reason": error.__class__.__name__}
    finally:
        db.close()


@celery_app.task(name="cybershield.dispatch_webhook_outbox", bind=True, max_retries=0)
def dispatch_webhook_outbox(self):
    """Lease due outbox rows then enqueue deliveries; no network I/O in the scheduler."""
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        rows = db.scalars(select(WebhookDelivery)
            .where(WebhookDelivery.status.in_(["QUEUED", "RETRY", "DISPATCHING", "SENDING"]),
                WebhookDelivery.next_attempt_at <= now)
            .order_by(WebhookDelivery.next_attempt_at)
            .with_for_update(skip_locked=True).limit(100)).all()
        ids = [row.id for row in rows]
        for row in rows:
            row.status = "DISPATCHING"
            row.next_attempt_at = now + timedelta(minutes=5)
        db.commit()
        queued = 0
        for delivery_id in ids:
            try:
                deliver_webhook.delay(str(delivery_id))
                queued += 1
            except Exception:
                row = db.get(WebhookDelivery, delivery_id)
                if row:
                    row.status = "QUEUED"
                    row.next_attempt_at = now + timedelta(seconds=15)
                    db.commit()
        return {"queued": queued}
    except Exception:
        db.rollback()
        return {"status": "dispatcher_failed"}
    finally:
        db.close()


@celery_app.task(name="cybershield.deliver_webhook", bind=True, max_retries=0)
def deliver_webhook(self, delivery_id: str):
    from app.models import ThreatWebhook, WebhookDelivery
    from app.services.webhooks import decrypt_secret, send_signed_webhook
    db = SessionLocal()
    try:
        try: delivery_uuid = UUID(delivery_id)
        except (ValueError, TypeError): return {"status": "invalid_delivery_id"}
        row = db.get(WebhookDelivery, delivery_uuid)
        if not row or row.status in {"DELIVERED", "FAILED", "CANCELLED"}:
            return {"status": "already_final"}
        hook = db.scalar(select(ThreatWebhook).where(ThreatWebhook.id == row.webhook_id,
            ThreatWebhook.organization_id == row.organization_id))
        if not hook or not hook.active:
            row.status = "CANCELLED"
            row.last_error = "WEBHOOK_DISABLED"
            db.commit()
            return {"status": "cancelled"}
        row.attempts += 1
        row.status = "SENDING"
        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.commit()
        try:
            secret = decrypt_secret(hook.secret_ciphertext)
            status_code = send_signed_webhook(hook.url, secret, row.event_type, row.payload or {})
            if 200 <= status_code < 300:
                row.status, row.last_error = "DELIVERED", None
                db.commit()
                return {"status": "delivered", "http_status": status_code}
            row.last_error = f"HTTP_{status_code}"
            if status_code >= 500 or status_code == 429:
                raise OSError(row.last_error)
            row.status = "FAILED"
            db.commit()
            return {"status": "failed", "reason": row.last_error}
        except Exception as error:
            db.rollback()
            row = db.get(WebhookDelivery, delivery_uuid)
            if not row: return {"status": "not_found"}
            row.last_error = error.__class__.__name__[:120]
            if row.attempts >= 5:
                row.status = "FAILED"
            else:
                row.status = "RETRY"
                row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(5 * (2 ** (row.attempts - 1)), 300))
            db.commit()
            return {"status": row.status.lower(), "attempts": row.attempts}
    finally:
        db.close()


@celery_app.task(name="cybershield.purge_expired_events", bind=True, max_retries=0)
def purge_expired_events(self):
    """Apply explicitly enabled org event policies; preserve linked evidence and all audit logs."""
    from datetime import timedelta
    from sqlalchemy import func
    from app.models import AlertEventLink, InvestigationLink
    db = SessionLocal()
    total = 0
    now = datetime.now(timezone.utc)
    try:
        policies = db.scalars(select(DataRetentionPolicy).where(DataRetentionPolicy.enabled.is_(True))).all()
        for policy in policies:
            cutoff = now - timedelta(days=policy.event_retention_days)
            alert_linked = select(AlertEventLink.id).where(
                AlertEventLink.organization_id == policy.organization_id,
                AlertEventLink.event_id == SecurityEvent.id).exists()
            investigation_linked = select(InvestigationLink.id).where(
                InvestigationLink.organization_id == policy.organization_id,
                InvestigationLink.resource_type == "EVENT",
                InvestigationLink.resource_id == cast(SecurityEvent.id, String)).exists()
            expired_ids = select(SecurityEvent.id).where(
                SecurityEvent.organization_id == policy.organization_id,
                SecurityEvent.event_timestamp < cutoff,
                SecurityEvent.processing_status == "PROCESSED",
                ~alert_linked, ~investigation_linked).limit(5000)
            result = db.execute(delete(SecurityEvent).where(SecurityEvent.id.in_(expired_ids)))
            deleted = max(0, result.rowcount or 0)
            if deleted:
                db.add(AuditLog(organization_id=policy.organization_id, actor_id=None,
                    action="EVENT_RETENTION_PURGED", resource="security_event", resource_id=None,
                    metadata_json={"deleted_count": deleted, "retention_days": policy.event_retention_days,
                        "cutoff": cutoff.isoformat(), "reason": "explicitly enabled organization retention policy"}))
                total += deleted
            db.commit()
        return {"deleted_events": total, "policies_applied": len(policies), "audit_logs_deleted": 0}
    except Exception as error:
        db.rollback()
        return {"status": "failed", "reason": error.__class__.__name__}
    finally:
        db.close()


@celery_app.task(name="cybershield.record_posture_snapshots", bind=True, max_retries=0)
def record_posture_snapshots(self):
    from sqlalchemy import func
    from app.services.scoring import calculate_score
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    created = 0
    try:
        for org in db.scalars(select(Organization)).all():
            existing = db.scalar(select(SecurityPostureSnapshot.id).where(
                SecurityPostureSnapshot.organization_id == org.id,
                SecurityPostureSnapshot.created_at >= day_start).limit(1))
            if existing: continue
            critical = db.scalar(select(func.count(Finding.id)).where(Finding.organization_id == org.id,
                Finding.severity == "CRITICAL", Finding.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))) or 0
            open_incidents = db.scalar(select(func.count(Incident.id)).where(Incident.organization_id == org.id,
                Incident.status.notin_(["RESOLVED", "CLOSED"]))) or 0
            avg_risk = db.scalar(select(func.avg(Risk.risk_score)).where(Risk.organization_id == org.id,
                Risk.status != "CLOSED")) or 0
            db.add(SecurityPostureSnapshot(organization_id=org.id,
                security_score=calculate_score(db, org.id), risk_score=int(avg_risk),
                critical_findings=critical, open_incidents=open_incidents,
                compliance_score=0))  # Compliance remains explicitly unassessed.
            db.commit()
            created += 1
        return {"snapshots_created": created, "generated_at": now.isoformat()}
    except Exception as error:
        db.rollback()
        return {"status": "failed", "reason": error.__class__.__name__}
    finally:
        db.close()
