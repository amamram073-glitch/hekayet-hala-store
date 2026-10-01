"""Development-only sample records. These example assets are not authorized to scan."""
import os
from sqlalchemy import select
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Asset, Finding, Incident, Membership, Organization, Risk, SecurityEvent, User
from app.security import hash_password


def main():
    if settings.environment != "development":
        raise SystemExit("Refusing to seed: set ENVIRONMENT=development explicitly")
    password = os.getenv("SEED_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Set SEED_PASSWORD to a 12+ character development-only password")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.scalar(select(Organization).where(Organization.name == "DEVELOPMENT DATA — Northstar"))
        if existing:
            raise SystemExit("Development seed already exists; no records changed")
        org = Organization(name="DEVELOPMENT DATA — Northstar")
        db.add(org); db.flush()
        users = []
        for email, name, role in [
            ("owner@example.com", "Development Owner", "ORGANIZATION_OWNER"),
            ("analyst@example.com", "Development Analyst", "SECURITY_ANALYST"),
            ("viewer@example.com", "Development Viewer", "VIEWER"),
        ]:
            user = User(email=email, full_name=name, password_hash=hash_password(password))
            db.add(user); db.flush()
            db.add(Membership(organization_id=org.id, user_id=user.id, role=role))
            users.append(user)
        assets=[]
        for n in range(1, 11):
            a=Asset(organization_id=org.id, name=f"Development asset {n}", hostname=f"asset{n}.example.com",
                    type="DOMAIN" if n%2 else "WEBSITE", environment="DEVELOPMENT",
                    authorization_status="PENDING", status="ACTIVE")
            db.add(a); assets.append(a)
        db.flush()
        for n, severity in enumerate(["CRITICAL", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW"], start=1):
            db.add(Finding(organization_id=org.id, asset_id=assets[n-1].id,
                title=f"DEVELOPMENT DATA — Example {severity.lower()} finding {n}",
                description="Development-only sample record; no live scan was performed.", severity=severity,
                category="CONFIGURATION", evidence={"seed_data": True},
                remediation="Replace with remediation derived from an authorized assessment."))
        db.add_all([
            Risk(organization_id=org.id, asset_id=assets[0].id, title="DEVELOPMENT DATA — Backup exposure", likelihood=3, impact=4, risk_score=12, owner="Development Analyst"),
            Incident(organization_id=org.id, title="DEVELOPMENT DATA — Sample incident", description="Development-only record.", severity="LOW"),
            SecurityEvent(organization_id=org.id, event_type="DEVELOPMENT_SEED", severity="INFO", message="DEVELOPMENT DATA seed created; no scan performed.", metadata_json={"development_data": True}),
        ])
        db.commit()
    print("DEVELOPMENT DATA created. All seeded assets are PENDING authorization; no scanner was run.")

if __name__ == "__main__":
    main()
