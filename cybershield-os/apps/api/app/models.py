from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def now_utc():
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Membership(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="ORGANIZATION_OWNER", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(32), default="VIEWER")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("organization_id", "hostname", name="uq_org_hostname"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="DOMAIN")
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), default="PRODUCTION")
    owner: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    authorization_status: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    authorization_statement: Mapped[str | None] = mapped_column(Text)
    authorized_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[object] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (Index("ix_finding_org_severity", "organization_id", "severity"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[object] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("scans.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(48), default="CONFIGURATION")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    remediation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    cve: Mapped[str | None] = mapped_column(String(24))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    likelihood: Mapped[int] = mapped_column(Integer, default=3)
    impact: Mapped[int] = mapped_column(Integer, default=3)
    risk_score: Mapped[int] = mapped_column(Integer, default=9)
    owner: Mapped[str | None] = mapped_column(String(160))
    treatment: Mapped[str] = mapped_column(String(24), default="MITIGATE")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    assigned_to: Mapped[str | None] = mapped_column(String(160))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[list] = mapped_column(JSON, default=list)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (Index("ix_event_org_timestamp", "organization_id", "event_timestamp"),
                      Index("ix_event_org_severity", "organization_id", "severity"),
                      Index("ix_event_org_status", "organization_id", "processing_status"),
                      Index("ix_event_asset_timestamp", "asset_id", "event_timestamp"))
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="INFO", index=True)
    source: Mapped[str] = mapped_column(String(120), default="CyberShield OS")
    source_type: Mapped[str] = mapped_column(String(32), default="APPLICATION", nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(253))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(320), index=True)
    asset_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="SET NULL"), index=True)
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    processing_status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_key_org_active", "organization_id", "revoked_at"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    per_minute_limit: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    window_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class DetectionRule(Base):
    __tablename__ = "detection_rules"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_detection_rule_org_name"),
                      Index("ix_detection_rule_org_enabled", "organization_id", "enabled"))
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_org_status_severity", "organization_id", "status", "severity"),
                      Index("ix_alert_org_created", "organization_id", "created_at"))
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    detection_rule_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("detection_rules.id", ondelete="SET NULL"), index=True)
    asset_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("assets.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(24), default="NEW", index=True)
    source: Mapped[str] = mapped_column(String(120), default="CyberShield Detection")
    username: Mapped[str | None] = mapped_column(String(320), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AlertEventLink(Base):
    __tablename__ = "alert_event_links"
    __table_args__ = (UniqueConstraint("alert_id", "event_id", name="uq_alert_event"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[object] = mapped_column(Uuid, ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[object] = mapped_column(Uuid, ForeignKey("security_events.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AlertNote(Base):
    __tablename__ = "alert_notes"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[object] = mapped_column(Uuid, ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ThreatIndicator(Base):
    __tablename__ = "threat_indicators"
    __table_args__ = (UniqueConstraint("organization_id", "type", "normalized_value", name="uq_indicator_org_value"),
                      Index("ix_indicator_org_type", "organization_id", "type"))
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(2048), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    source: Mapped[str] = mapped_column(String(160), default="Organization", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (Index("ix_investigation_org_status", "organization_id", "status"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    assigned_to_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestigationLink(Base):
    __tablename__ = "investigation_links"
    __table_args__ = (UniqueConstraint("organization_id", "investigation_id", "resource_type", "resource_id", name="uq_investigation_resource"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[object] = mapped_column(Uuid, ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(24), index=True)
    resource_id: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EvidenceMetadata(Base):
    __tablename__ = "evidence_metadata"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[object] = mapped_column(Uuid, ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_reference: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class InvestigationNote(Base):
    __tablename__ = "investigation_notes"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[object] = mapped_column(Uuid, ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SecurityCase(Base):
    __tablename__ = "security_cases"
    __table_args__ = (UniqueConstraint("organization_id", "case_number", name="uq_case_org_number"),
                      Index("ix_case_org_status", "organization_id", "status"))
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    owner_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    incident_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("incidents.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class CaseResourceLink(Base):
    __tablename__ = "case_resource_links"
    __table_args__ = (UniqueConstraint("organization_id", "case_id", "resource_type", "resource_id", name="uq_case_resource"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid, ForeignKey("security_cases.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(24), index=True)
    resource_id: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CaseNote(Base):
    __tablename__ = "case_notes"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid, ForeignKey("security_cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AnalystTask(Base):
    __tablename__ = "analyst_tasks"
    __table_args__ = (Index("ix_task_org_assignee_status", "organization_id", "assigned_to_id", "status"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    investigation_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("security_cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    assigned_to_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="TODO", index=True)
    created_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Playbook(Base):
    __tablename__ = "playbooks"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_playbook_org_name"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    trigger: Mapped[str] = mapped_column(String(200), default="MANUAL")
    steps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    approved_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    execution_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ThreatWebhook(Base):
    __tablename__ = "threat_webhooks"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    webhook_id: Mapped[object] = mapped_column(Uuid, ForeignKey("threat_webhooks.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    last_error: Mapped[str | None] = mapped_column(String(120))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "period", name="uq_ai_usage_period"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[str] = mapped_column(String(7), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SecurityPostureSnapshot(Base):
    __tablename__ = "security_posture_snapshots"
    __table_args__ = (Index("ix_posture_org_created", "organization_id", "created_at"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    security_score: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[int] = mapped_column(Integer)
    critical_findings: Mapped[int] = mapped_column(Integer)
    open_incidents: Mapped[int] = mapped_column(Integer)
    compliance_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_retention_org"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    event_retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user_read", "organization_id", "user_id", "read_at"),)
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notification_type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(600), default="")
    resource_type: Mapped[str | None] = mapped_column(String(48))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    before_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    report_type: Mapped[str] = mapped_column(String(48), default="EXECUTIVE")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AiConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AiMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[object] = mapped_column(Uuid, ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
