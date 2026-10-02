from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterInput(StrictInput):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=180)


class LoginInput(StrictInput):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AssetCreate(StrictInput):
    name: str = Field(min_length=2, max_length=180)
    type: str = Field(default="DOMAIN", pattern="^(DOMAIN|SUBDOMAIN|WEBSITE|SERVER|APPLICATION|API|ENDPOINT|IP)$")
    hostname: str = Field(min_length=3, max_length=253)
    environment: str = Field(default="PRODUCTION", max_length=32)
    owner: str | None = Field(default=None, max_length=160)

    @field_validator("hostname")
    @classmethod
    def normalize_hostname(cls, value: str) -> str:
        value = value.strip().rstrip(".").lower()
        if "://" in value or "/" in value or "@" in value:
            raise ValueError("Enter a hostname only; URL paths and schemes are not accepted")
        return value.encode("idna").decode("ascii")


class AssetUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    type: str | None = Field(default=None, pattern="^(DOMAIN|SUBDOMAIN|WEBSITE|SERVER|APPLICATION|API|ENDPOINT|IP)$")
    environment: str | None = Field(default=None, max_length=32)
    owner: str | None = Field(default=None, max_length=160)


class AuthorizationInput(StrictInput):
    confirmed: bool
    statement: str = Field(min_length=30, max_length=1000)


class FindingUpdate(StrictInput):
    status: str = Field(pattern="^(OPEN|ACKNOWLEDGED|IN_PROGRESS|RESOLVED|FALSE_POSITIVE)$")


class RiskCreate(StrictInput):
    title: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=5000)
    asset_id: str | None = None
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    owner: str | None = Field(default=None, max_length=160)
    treatment: str = Field(default="MITIGATE", pattern="^(MITIGATE|ACCEPT|TRANSFER|AVOID)$")
    deadline: datetime | None = None


class RiskUpdate(StrictInput):
    status: str | None = Field(default=None, pattern="^(OPEN|IN_PROGRESS|CLOSED)$")
    treatment: str | None = Field(default=None, pattern="^(MITIGATE|ACCEPT|TRANSFER|AVOID)$")
    owner: str | None = Field(default=None, max_length=160)
    deadline: datetime | None = None


class IncidentCreate(StrictInput):
    title: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=5000)
    severity: str = Field(default="MEDIUM", pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$")
    assigned_to: str | None = Field(default=None, max_length=160)


class IncidentUpdate(StrictInput):
    status: str = Field(pattern="^(OPEN|INVESTIGATING|CONTAINED|RESOLVED|CLOSED)$")


class AiQuestion(StrictInput):
    question: str = Field(min_length=3, max_length=4000)
    conversation_id: str | None = None


class ApiKeyCreate(StrictInput):
    name: str = Field(min_length=2, max_length=120)
    permissions: list[str] = Field(min_length=1, max_length=4)

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, values: list[str]) -> list[str]:
        allowed = {"EVENT_INGEST", "ASSET_READ", "FINDING_READ", "REPORT_READ"}
        if not set(values) <= allowed or len(set(values)) != len(values):
            raise ValueError("Unsupported or duplicate API key permission")
        return values


class EventIngestInput(StrictInput):
    source: str = Field(min_length=1, max_length=120)
    source_type: str = Field(pattern="^(APPLICATION|WEB_SERVER|AUTHENTICATION|ENDPOINT|CLOUD|FIREWALL|DNS|API)$")
    event_type: str = Field(min_length=2, max_length=64, pattern="^[A-Za-z0-9_.:-]+$")
    severity: str = Field(default="INFO", pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$")
    timestamp: datetime | None = None
    hostname: str | None = Field(default=None, max_length=253)
    ip_address: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=320)
    asset_id: str | None = Field(default=None, max_length=36)
    message: str = Field(min_length=1, max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json
        if len(json.dumps(value, default=str)) > 12000:
            raise ValueError("Event metadata exceeds 12 KB")
        return value


class DetectionCondition(StrictInput):
    field: str = Field(pattern="^(event_type|source_type|severity|hostname|username|ip_address|message)$")
    operator: str = Field(pattern="^(eq|contains|in)$")
    value: str | list[str] = Field(min_length=1, max_length=500)


class DetectionRuleCreate(StrictInput):
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    severity: str = Field(default="MEDIUM", pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$")
    enabled: bool = True
    conditions: list[DetectionCondition] = Field(min_length=1, max_length=10)
    match_count: int = Field(default=1, ge=1, le=100)
    window_minutes: int = Field(default=5, ge=1, le=1440)


class DetectionRuleUpdate(StrictInput):
    description: str | None = Field(default=None, max_length=2000)
    severity: str | None = Field(default=None, pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$")
    enabled: bool | None = None
    conditions: list[DetectionCondition] | None = Field(default=None, min_length=1, max_length=10)
    match_count: int | None = Field(default=None, ge=1, le=100)
    window_minutes: int | None = Field(default=None, ge=1, le=1440)


class AlertUpdate(StrictInput):
    status: str = Field(pattern="^(NEW|ACKNOWLEDGED|INVESTIGATING|RESOLVED|FALSE_POSITIVE)$")


class AlertNoteCreate(StrictInput):
    content: str = Field(min_length=1, max_length=5000)


class IndicatorCreate(StrictInput):
    type: str = Field(pattern="^(IP|DOMAIN|URL|HASH|EMAIL)$")
    value: str = Field(min_length=1, max_length=2048)
    confidence: int = Field(default=50, ge=0, le=100)
    source: str = Field(default="Organization", min_length=1, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=2000)


class InvestigationCreate(StrictInput):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=5000)
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    assigned_to_id: str | None = None
    alert_id: str | None = None


class InvestigationUpdate(StrictInput):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    priority: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    status: str | None = Field(default=None, pattern="^(OPEN|INVESTIGATING|CONTAINED|RESOLVED|CLOSED)$")
    assigned_to_id: str | None = None


class InvestigationLinkCreate(StrictInput):
    resource_type: str = Field(pattern="^(ALERT|EVENT|ASSET|FINDING|INCIDENT|CASE)$")
    resource_id: str = Field(min_length=1, max_length=80)


class CaseCreate(StrictInput):
    title: str = Field(min_length=3, max_length=240)
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    incident_id: str | None = None
    owner_id: str | None = None


class CaseUpdate(StrictInput):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    priority: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    status: str | None = Field(default=None, pattern="^(OPEN|IN_PROGRESS|RESOLVED|CLOSED)$")
    owner_id: str | None = None


class CaseLinkCreate(StrictInput):
    resource_type: str = Field(pattern="^(ALERT|EVENT|ASSET|FINDING|INCIDENT|INVESTIGATION|TASK|EVIDENCE)$")
    resource_id: str = Field(min_length=1, max_length=80)


class CaseNoteCreate(StrictInput):
    note: str = Field(min_length=1, max_length=5000)


class TaskCreate(StrictInput):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=5000)
    investigation_id: str | None = None
    case_id: str | None = None
    assigned_to_id: str | None = None
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    due_date: datetime | None = None


class TaskUpdate(StrictInput):
    status: str | None = Field(default=None, pattern="^(TODO|IN_PROGRESS|DONE)$")
    priority: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    assigned_to_id: str | None = None
    due_date: datetime | None = None


class InvestigationNoteCreate(StrictInput):
    note: str = Field(min_length=1, max_length=5000)


class PlaybookCreate(StrictInput):
    name: str = Field(min_length=3, max_length=160)
    trigger: str = Field(min_length=3, max_length=200)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=25)
    enabled: bool = True

    @field_validator("steps")
    @classmethod
    def safe_steps(cls, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {"CREATE_TASK", "CREATE_INCIDENT", "SET_ALERT_STATUS", "REQUEST_APPROVAL", "NOTIFY_WEBHOOK", "GENERATE_REPORT"}
        for step in values:
            if not isinstance(step, dict) or set(step) - {"type", "label", "config", "condition"}:
                raise ValueError("Playbook step contains unsupported fields")
            if step.get("type") not in allowed:
                raise ValueError("Unsupported playbook step type")
            if not isinstance(step.get("config", {}), dict) or len(str(step.get("config", {}))) > 4000:
                raise ValueError("Playbook step config is invalid or too large")
            if "condition" in step and (not isinstance(step["condition"], dict) or len(str(step["condition"])) > 1000):
                raise ValueError("Playbook condition must be bounded structured data")
        return values


class PlaybookUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    trigger: str | None = Field(default=None, min_length=3, max_length=200)
    steps: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=25)
    enabled: bool | None = None

    @field_validator("steps")
    @classmethod
    def safe_steps(cls, values: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if values is None: return None
        return PlaybookCreate.safe_steps(values)


class ApprovalCreate(StrictInput):
    action_type: str = Field(min_length=3, max_length=80)
    action_payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(StrictInput):
    status: str = Field(pattern="^(APPROVED|REJECTED)$")
    note: str = Field(default="", max_length=2000)


class RetentionPolicyUpdate(StrictInput):
    event_retention_days: Literal[30, 90, 180, 365]
    enabled: bool


class WebhookCreate(StrictInput):
    url: str = Field(min_length=8, max_length=2048)
    secret: str = Field(min_length=32, max_length=256)
    event_types: list[str] = Field(min_length=1, max_length=10)

    @field_validator("event_types")
    @classmethod
    def valid_webhook_event_types(cls, values: list[str]) -> list[str]:
        allowed = {"ALERT_CREATED", "INCIDENT_CREATED", "SCAN_COMPLETED", "HIGH_SEVERITY_EVENT", "*"}
        if not set(values) <= allowed or len(set(values)) != len(values):
            raise ValueError("Unsupported or duplicate webhook event type")
        return values


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
