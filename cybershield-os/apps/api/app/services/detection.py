from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Alert, AlertEventLink, DetectionRule, SecurityEvent, ThreatIndicator, now_utc


def _event_value(event: SecurityEvent, field: str):
    if field == "severity": return event.severity
    if field == "hostname": return event.hostname or ""
    if field == "ip_address": return event.ip_address or ""
    if field == "username": return event.username or ""
    if field == "message": return event.message or ""
    if field == "source_type": return event.source_type
    if field == "event_type": return event.event_type
    return ""


def _matches(event: SecurityEvent, conditions: list[dict]) -> bool:
    for condition in conditions:
        value = str(_event_value(event, condition["field"])).casefold()
        expected = condition.get("value")
        operator = condition.get("operator")
        if operator == "eq" and value != str(expected).casefold(): return False
        if operator == "contains" and str(expected).casefold() not in value: return False
        if operator == "in" and value not in {str(x).casefold() for x in expected}: return False
    return True


def _create_alert(db: Session, event: SecurityEvent, title: str, severity: str, reason: str,
                  recommendation: str, rule_id=None, risk_score: int = 50) -> Alert | None:
    recent = now_utc() - timedelta(hours=1)
    query = select(Alert).where(Alert.organization_id == event.organization_id,
                                Alert.title == title, Alert.created_at >= recent,
                                Alert.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))
    existing = db.scalar(query)
    if existing:
        link = db.scalar(select(AlertEventLink).where(AlertEventLink.organization_id == event.organization_id,
            AlertEventLink.alert_id == existing.id, AlertEventLink.event_id == event.id))
        if not link:
            db.add(AlertEventLink(organization_id=event.organization_id, alert_id=existing.id, event_id=event.id))
            existing.last_seen_at = event.event_timestamp
        return existing
    alert = Alert(organization_id=event.organization_id, detection_rule_id=rule_id,
        asset_id=event.asset_id, title=title, description=reason, reason=reason,
        severity=severity, status="NEW", source=event.source, username=event.username,
        risk_score=max(0, min(100, risk_score)), recommendation=recommendation,
        first_seen_at=event.event_timestamp, last_seen_at=event.event_timestamp)
    db.add(alert)
    db.flush()
    db.add(AlertEventLink(organization_id=event.organization_id, alert_id=alert.id, event_id=event.id))
    from app.services.webhooks import create_delivery_rows
    create_delivery_rows(db, event.organization_id, "ALERT_CREATED", {
        "type": "ALERT_CREATED", "organization_id": str(event.organization_id),
        "alert_id": str(alert.id), "title": alert.title, "severity": alert.severity,
        "risk_score": alert.risk_score, "reason": alert.reason,
        "occurred_at": alert.created_at,
    })
    return alert


def evaluate_event(db: Session, event: SecurityEvent) -> list[Alert]:
    """Evaluate allowlisted rules only; no user-supplied code or expressions are executed."""
    alerts: list[Alert] = []
    enabled_rules = db.scalars(select(DetectionRule).where(
        DetectionRule.organization_id == event.organization_id, DetectionRule.enabled.is_(True))).all()
    for rule in enabled_rules:
        conditions = (rule.conditions or {}).get("conditions", [])
        if not conditions or not _matches(event, conditions):
            continue
        window_minutes = int((rule.conditions or {}).get("window_minutes", 5))
        cutoff = now_utc() - timedelta(minutes=max(1, min(window_minutes, 1440)))
        historical = db.scalars(select(SecurityEvent).where(
            SecurityEvent.organization_id == event.organization_id,
            SecurityEvent.event_timestamp >= cutoff).order_by(SecurityEvent.event_timestamp.desc()).limit(500)).all()
        matched = [row for row in historical if _matches(row, conditions)]
        threshold = int((rule.conditions or {}).get("match_count", 1))
        if len(matched) >= threshold:
            alert = _create_alert(db, event, rule.name, rule.severity,
                f"Rule matched {len(matched)} event(s) in a {window_minutes}-minute window. Evidence is potentially suspicious and requires analyst review.",
                "Review the linked events and validate the account, host, and expected operational context.",
                rule.id, min(95, 35 + len(matched) * 8))
            if alert:
                for matched_event in matched:
                    if matched_event.id == event.id:
                        continue
                    exists = db.scalar(select(AlertEventLink.id).where(
                        AlertEventLink.organization_id == event.organization_id,
                        AlertEventLink.alert_id == alert.id,
                        AlertEventLink.event_id == matched_event.id))
                    if not exists:
                        db.add(AlertEventLink(organization_id=event.organization_id,
                            alert_id=alert.id, event_id=matched_event.id))
                        db.flush()
                alerts.append(alert)

    kind = event.event_type.upper()
    if kind in {"PRIVILEGED_ACCOUNT_ACTIVITY", "PRIVILEGED_ACTION"}:
        alert = _create_alert(db, event, "Privileged account activity", "HIGH",
            "A privileged-account event was reported. This is a review signal, not a conclusion of malicious activity.",
            "Confirm the actor, change request, and expected administrative window.", risk_score=68)
        if alert: alerts.append(alert)
    if kind in {"SUSPICIOUS_CONFIGURATION_CHANGE", "CONFIGURATION_CHANGE"} and event.severity in {"HIGH", "CRITICAL"}:
        alert = _create_alert(db, event, "High-severity configuration change", event.severity,
            "A high-severity configuration-change event requires validation against the approved change record.",
            "Compare the change with the organization's authorized configuration and rollback process.", risk_score=75)
        if alert: alerts.append(alert)
    if kind in {"FINDINGS_DETECTED", "VULNERABILITIES_DETECTED"} and event.severity in {"HIGH", "CRITICAL"}:
        alert = _create_alert(db, event, "Critical vulnerability activity", event.severity,
            "A high or critical finding event was recorded by the assessment workflow.",
            "Review the finding evidence and remediation guidance for the authorized asset.", risk_score=80)
        if alert: alerts.append(alert)

    if kind in {"AUTH_FAILURE", "LOGIN_FAILED", "AUTHENTICATION_FAILURE", "FAILED_LOGIN"}:
        cutoff = now_utc() - timedelta(minutes=10)
        matches = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == event.organization_id,
            SecurityEvent.event_timestamp >= cutoff,
            SecurityEvent.event_type.in_(["AUTH_FAILURE", "LOGIN_FAILED", "AUTHENTICATION_FAILURE", "FAILED_LOGIN"]),
            SecurityEvent.username == event.username).limit(100)).all()
        if len(matches) >= 5:
            alert = _create_alert(db, event, "Repeated authentication failures", "HIGH",
                f"{len(matches)} failed-authentication events for this account were observed within ten minutes.",
                "Verify the user, source IP, and sign-in activity; follow the organization's account-response process.", risk_score=72)
            if alert: alerts.append(alert)

    if kind in {"PRIVILEGED_ACCOUNT_ACTIVITY", "PRIVILEGED_ACTION"} and event.username:
        cutoff = now_utc() - timedelta(minutes=30)
        related = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == event.organization_id,
            SecurityEvent.event_timestamp >= cutoff, SecurityEvent.username == event.username).limit(200)).all()
        types = {row.event_type.upper() for row in related}
        failures = {"AUTH_FAILURE", "LOGIN_FAILED", "AUTHENTICATION_FAILURE", "FAILED_LOGIN"}
        success = {"AUTH_SUCCESS", "LOGIN_SUCCESS", "AUTHENTICATION_SUCCESS"}
        if types.intersection(failures) and types.intersection(success):
            alert = _create_alert(db, event, "Correlated authentication and privileged activity", "CRITICAL",
                "Potentially suspicious activity: failed authentication, a successful login, and privileged activity for the same account occurred within 30 minutes. Correlation is not proof of compromise.",
                "Review the linked account timeline, source addresses, and approved change records before taking action.", risk_score=88)
            if alert:
                for row in related:
                    if row.event_type.upper() in failures | success | {"PRIVILEGED_ACCOUNT_ACTIVITY", "PRIVILEGED_ACTION"}:
                        db.add(AlertEventLink(organization_id=event.organization_id, alert_id=alert.id, event_id=row.id))
                alerts.append(alert)

    candidates = {"IP": event.ip_address, "DOMAIN": event.hostname}
    for key in ("url", "hash", "email"):
        value = (event.metadata_json or {}).get(key)
        if isinstance(value, str): candidates[key.upper()] = value.strip().lower()
    for indicator_type, value in candidates.items():
        if not value: continue
        normalized = value.strip().lower().rstrip(".")
        indicators = db.scalars(select(ThreatIndicator).where(
            ThreatIndicator.organization_id == event.organization_id,
            ThreatIndicator.type == indicator_type,
            ThreatIndicator.normalized_value == normalized)).all()
        for indicator in indicators:
            indicator.last_seen_at = event.event_timestamp
            alert = _create_alert(db, event, f"Threat indicator match: {indicator.type}", "HIGH",
                f"An event matched an organization-managed indicator from {indicator.source} (confidence {indicator.confidence}%). A match alone does not establish malicious activity.",
                "Validate indicator provenance and inspect the related event and affected asset.", risk_score=min(95, 40 + indicator.confidence // 2))
            if alert: alerts.append(alert)
    event.processing_status = "PROCESSED"
    return alerts
