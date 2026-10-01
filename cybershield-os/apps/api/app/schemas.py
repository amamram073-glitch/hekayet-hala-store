from datetime import datetime
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


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
