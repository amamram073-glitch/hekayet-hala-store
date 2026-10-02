"""Interactively create the first organization owner after applying migrations."""
from getpass import getpass
from sqlalchemy import func, select
from app.db import SessionLocal
from app.models import AuditLog, Membership, Organization, User
from app.security import hash_password


def main():
    email = input("Owner email: ").strip().lower()
    full_name = input("Owner full name: ").strip()
    organization_name = input("Organization name: ").strip()
    password = getpass("Owner password (min 12 chars): ")
    confirmation = getpass("Repeat password: ")
    if not email or not full_name or not organization_name:
        raise SystemExit("Email, name, and organization are required")
    if len(password) < 12 or password != confirmation:
        raise SystemExit("Password must be at least 12 characters and match confirmation")
    with SessionLocal() as db:
        if (db.scalar(select(func.count(Organization.id))) or 0) > 0:
            raise SystemExit("Bootstrap refused: an organization already exists")
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("Bootstrap refused: this user already exists")
        user = User(email=email, full_name=full_name, password_hash=hash_password(password))
        organization = Organization(name=organization_name)
        db.add_all([user, organization])
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=organization.id, role="ORGANIZATION_OWNER"))
        db.add(AuditLog(organization_id=organization.id, actor_id=user.id,
            action="INITIAL_OWNER_BOOTSTRAPPED", resource="organization",
            resource_id=str(organization.id), after_state={"owner_email": email}))
        db.commit()
        print(f"Initial owner created for organization {organization.name!r}. Sign in through the website.")


if __name__ == "__main__":
    main()
