from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AuditLog
from app.security import Principal, get_principal, require_roles


def audit(db: Session, principal: Principal, request: Request, action: str, resource: str,
          resource_id: str | None = None, metadata: dict | None = None):
    details = dict(metadata or {})
    before_state = details.pop("before_state", None)
    after_state = details.pop("after_state", None)
    if before_state is None and "before" in details: before_state = {"status": details["before"]}
    if after_state is None and "after" in details: after_state = {"status": details["after"]}
    db.add(AuditLog(organization_id=principal.organization_id, actor_id=principal.user.id,
                    action=action, resource=resource, resource_id=resource_id,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent", "")[:300],
                    request_id=getattr(request.state, "request_id", None),
                    before_state=before_state or {}, after_state=after_state or {},
                    metadata_json=details))


def manager(principal: Principal = Depends(require_roles("ORGANIZATION_OWNER", "SECURITY_ADMIN", "IT_ADMIN"))):
    return principal


def analyst(principal: Principal = Depends(require_roles("ORGANIZATION_OWNER", "SECURITY_ADMIN", "SECURITY_ANALYST", "IT_ADMIN"))):
    return principal
