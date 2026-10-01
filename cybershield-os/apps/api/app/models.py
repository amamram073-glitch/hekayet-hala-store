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
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="INFO")
    source: Mapped[str] = mapped_column(String(120), default="CyberShield OS")
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
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
