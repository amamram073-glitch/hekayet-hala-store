from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AuditLog
from app.security import Principal, get_principal, require_roles


def audit(db: Session, principal: Principal, request: Request, action: str, resource: str,
          resource_id: str | None = None, metadata: dict | None = None):
    db.add(AuditLog(organization_id=principal.organization_id, actor_id=principal.user.id,
                    action=action, resource=resource, resource_id=resource_id,
                    ip_address=request.client.host if request.client else None,
                    metadata_json=metadata or {}))


def manager(principal: Principal = Depends(require_roles("ORGANIZATION_OWNER", "SECURITY_ADMIN", "IT_ADMIN"))):
    return principal


def analyst(principal: Principal = Depends(require_roles("ORGANIZATION_OWNER", "SECURITY_ADMIN", "SECURITY_ANALYST", "IT_ADMIN"))):
    return principal
