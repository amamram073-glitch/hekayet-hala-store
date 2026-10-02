from datetime import datetime, timezone
from secrets import token_hex
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import analyst, audit, manager
from app.models import (Alert, AnalystTask, ApprovalRequest, Asset, AuditLog, CaseNote, CaseResourceLink,
    EvidenceMetadata, Finding, Incident, Investigation, InvestigationLink, InvestigationNote, Membership, Notification,
    Playbook, SecurityCase, SecurityEvent, User)
from app.schemas import (AlertUpdate, ApprovalCreate, ApprovalDecision, CaseCreate, CaseLinkCreate, CaseNoteCreate, CaseUpdate, IncidentCreate,
    InvestigationCreate, InvestigationLinkCreate, InvestigationNoteCreate,
    InvestigationUpdate, PlaybookCreate, PlaybookUpdate, TaskCreate, TaskUpdate)
from app.security import Principal

router = APIRouter(tags=["investigations, cases and analyst workflow"])


def _notify_assignee(db, organization_id, user_id, actor_id, notification_type, title, message, resource_type, resource_id):
    if not user_id or user_id == actor_id: return None
    row = Notification(organization_id=organization_id, user_id=user_id,
        notification_type=notification_type, title=title, message=message[:600],
        resource_type=resource_type, resource_id=str(resource_id))
    db.add(row)
    return row


def _publish_notification(org_id, user_id, notification_id, notification_type, title, resource_type, resource_id):
    if not notification_id: return
    try:
        from app.services.realtime import publish_org_event
        publish_org_event(str(org_id), {"type": "notification", "recipient_id": str(user_id),
            "notification_id": str(notification_id), "notification_type": notification_type,
            "title": title, "resource_type": resource_type, "resource_id": str(resource_id)})
    except Exception:
        pass


def _id(value: str | None, label: str):
    if value is None: return None
    try: return UUID(value)
    except ValueError: raise HTTPException(status_code=404, detail=f"{label} not found")


def _member(db: Session, org, user_id: UUID | None):
    if user_id is None: return None
    member = db.scalar(select(Membership).where(Membership.organization_id == org,
        Membership.user_id == user_id, Membership.status == "ACTIVE"))
    if not member: raise HTTPException(status_code=422, detail="Assignee must be an active member of this organization")
    return member.user_id


def _investigation_view(row):
    return {"id": str(row.id), "title": row.title, "description": row.description,
        "priority": row.priority, "status": row.status,
        "assigned_to_id": str(row.assigned_to_id) if row.assigned_to_id else None,
        "created_at": row.created_at, "updated_at": row.updated_at, "resolved_at": row.resolved_at}


def _case_view(row):
    return {"id": str(row.id), "case_number": row.case_number, "title": row.title,
        "priority": row.priority, "status": row.status,
        "owner_id": str(row.owner_id) if row.owner_id else None,
        "incident_id": str(row.incident_id) if row.incident_id else None,
        "created_at": row.created_at, "updated_at": row.updated_at}


def _task_view(row):
    return {"id": str(row.id), "title": row.title, "description": row.description,
        "investigation_id": str(row.investigation_id) if row.investigation_id else None,
        "case_id": str(row.case_id) if row.case_id else None,
        "assigned_to_id": str(row.assigned_to_id) if row.assigned_to_id else None,
        "priority": row.priority, "due_date": row.due_date, "status": row.status,
        "created_at": row.created_at, "updated_at": row.updated_at}


@router.get("/investigations")
def list_investigations(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    rows = db.scalars(select(Investigation).where(Investigation.organization_id == principal.organization_id)
        .order_by(Investigation.updated_at.desc()).limit(200)).all()
    return [_investigation_view(row) for row in rows]


@router.post("/investigations", status_code=201)
def create_investigation(data: InvestigationCreate, request: Request,
                         principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    assignee = _member(db, principal.organization_id, _id(data.assigned_to_id, "User"))
    row = Investigation(organization_id=principal.organization_id, title=data.title,
        description=data.description, priority=data.priority, status="INVESTIGATING" if assignee else "OPEN",
        assigned_to_id=assignee, created_by_id=principal.user.id)
    db.add(row)
    db.flush()
    notification = _notify_assignee(db, principal.organization_id, assignee, principal.user.id,
        "INVESTIGATION_ASSIGNED", "Investigation assigned", row.title, "investigation", row.id)
    if data.alert_id:
        alert_id = _id(data.alert_id, "Alert")
        alert = db.scalar(select(Alert).where(Alert.id == alert_id,
            Alert.organization_id == principal.organization_id))
        if not alert: raise HTTPException(status_code=404, detail="Alert not found")
        db.add(InvestigationLink(organization_id=principal.organization_id,
            investigation_id=row.id, resource_type="ALERT", resource_id=str(alert.id)))
    audit(db, principal, request, "INVESTIGATION_CREATED", "investigation", str(row.id))
    if notification: db.flush()
    db.commit()
    _publish_notification(principal.organization_id, assignee, notification.id if notification else None,
        "INVESTIGATION_ASSIGNED", "Investigation assigned", "investigation", row.id)
    return _investigation_view(row)


@router.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid = _id(investigation_id, "Investigation")
    row = db.scalar(select(Investigation).where(Investigation.id == iid,
        Investigation.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Investigation not found")
    links = db.scalars(select(InvestigationLink).where(InvestigationLink.organization_id == principal.organization_id,
        InvestigationLink.investigation_id == row.id).order_by(InvestigationLink.created_at.asc()).limit(500)).all()
    tasks = db.scalars(select(AnalystTask).where(AnalystTask.organization_id == principal.organization_id,
        AnalystTask.investigation_id == row.id).order_by(AnalystTask.created_at.desc()).limit(200)).all()
    evidence = db.scalars(select(EvidenceMetadata).where(EvidenceMetadata.organization_id == principal.organization_id,
        EvidenceMetadata.investigation_id == row.id).order_by(EvidenceMetadata.created_at.asc()).limit(200)).all()
    notes = db.scalars(select(InvestigationNote).where(InvestigationNote.organization_id == principal.organization_id,
        InvestigationNote.investigation_id == row.id).order_by(InvestigationNote.created_at.asc()).limit(500)).all()
    timeline = []
    for link in links:
        timeline.append({"type": link.resource_type.lower(), "resource_id": link.resource_id, "at": link.created_at})
    for task in tasks:
        timeline.append({"type": "task", "resource_id": str(task.id), "label": task.title, "at": task.created_at})
    for note in notes:
        timeline.append({"type": "note", "resource_id": str(note.id), "label": note.note, "at": note.created_at})
    timeline.sort(key=lambda x: x["at"])
    return {**_investigation_view(row), "links": [{"id": str(l.id), "resource_type": l.resource_type,
        "resource_id": l.resource_id, "created_at": l.created_at} for l in links],
        "tasks": [_task_view(t) for t in tasks],
        "evidence": [{"id": str(e.id), "filename": e.filename, "media_type": e.media_type,
            "sha256": e.sha256, "storage_reference": e.storage_reference, "notes": e.notes,
            "created_at": e.created_at} for e in evidence], "timeline": timeline}


@router.patch("/investigations/{investigation_id}")
def update_investigation(investigation_id: str, data: InvestigationUpdate, request: Request,
                         principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid = _id(investigation_id, "Investigation")
    row = db.scalar(select(Investigation).where(Investigation.id == iid,
        Investigation.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Investigation not found")
    values = data.model_dump(exclude_unset=True)
    if "assigned_to_id" in values:
        values["assigned_to_id"] = _member(db, principal.organization_id, _id(values["assigned_to_id"], "User"))
    for field, value in values.items(): setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    if row.status in {"RESOLVED", "CLOSED"}: row.resolved_at = row.updated_at
    elif "status" in values: row.resolved_at = None
    audit(db, principal, request, "INVESTIGATION_UPDATED", "investigation", str(row.id), {"fields": list(values)})
    db.commit()
    return _investigation_view(row)


@router.post("/investigations/{investigation_id}/links", status_code=201)
def link_investigation(investigation_id: str, data: InvestigationLinkCreate, request: Request,
                       principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid = _id(investigation_id, "Investigation")
    investigation = db.scalar(select(Investigation).where(Investigation.id == iid,
        Investigation.organization_id == principal.organization_id))
    if not investigation: raise HTTPException(status_code=404, detail="Investigation not found")
    resource_id = data.resource_id
    model = {"ALERT": Alert, "EVENT": SecurityEvent, "ASSET": Asset,
             "FINDING": Finding, "INCIDENT": Incident, "CASE": SecurityCase}[data.resource_type]
    rid = _id(resource_id, data.resource_type.title())
    resource = db.scalar(select(model).where(model.id == rid, model.organization_id == principal.organization_id))
    if not resource: raise HTTPException(status_code=404, detail=f"{data.resource_type.title()} not found")
    row = InvestigationLink(organization_id=principal.organization_id, investigation_id=iid,
        resource_type=data.resource_type, resource_id=str(rid))
    db.add(row)
    audit(db, principal, request, "INVESTIGATION_RESOURCE_LINKED", "investigation", str(iid),
        {"resource_type": data.resource_type, "resource_id": str(rid)})
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Resource is already linked to this investigation")
    return {"id": str(row.id), "resource_type": row.resource_type, "resource_id": row.resource_id}


@router.post("/investigations/{investigation_id}/notes", status_code=201)
def add_investigation_note(investigation_id: str, data: InvestigationNoteCreate, request: Request,
                           principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid = _id(investigation_id, "Investigation")
    row = db.scalar(select(Investigation).where(Investigation.id == iid,
        Investigation.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Investigation not found")
    note = InvestigationNote(organization_id=principal.organization_id, investigation_id=iid,
        user_id=principal.user.id, note=data.note)
    db.add(note)
    audit(db, principal, request, "INVESTIGATION_NOTE_ADDED", "investigation", str(iid))
    db.commit()
    return {"id": str(note.id), "note": data.note, "created_at": note.created_at}


@router.get("/cases")
def list_cases(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    rows = db.scalars(select(SecurityCase).where(SecurityCase.organization_id == principal.organization_id)
        .order_by(SecurityCase.created_at.desc()).limit(200)).all()
    return [_case_view(row) for row in rows]


@router.post("/cases", status_code=201)
def create_case(data: CaseCreate, request: Request, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    owner = _member(db, principal.organization_id, _id(data.owner_id, "User"))
    incident = None
    if data.incident_id:
        incident_id = _id(data.incident_id, "Incident")
        incident = db.scalar(select(Incident).where(Incident.id == incident_id,
            Incident.organization_id == principal.organization_id))
        if not incident: raise HTTPException(status_code=404, detail="Incident not found")
    row = SecurityCase(organization_id=principal.organization_id,
        case_number=f"CS-{datetime.now(timezone.utc):%y%m%d}-{token_hex(3).upper()}",
        title=data.title, priority=data.priority, status="OPEN", owner_id=owner,
        incident_id=incident.id if incident else None)
    db.add(row)
    db.flush()
    audit(db, principal, request, "CASE_CREATED", "case", str(row.id), {"case_number": row.case_number})
    db.commit()
    return _case_view(row)


@router.get("/cases/{case_id}")
def get_case(case_id: str, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    cid = _id(case_id, "Case")
    row = db.scalar(select(SecurityCase).where(SecurityCase.id == cid,
        SecurityCase.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Case not found")
    links = db.scalars(select(CaseResourceLink).where(CaseResourceLink.organization_id == principal.organization_id,
        CaseResourceLink.case_id == row.id).order_by(CaseResourceLink.created_at.asc()).limit(500)).all()
    notes = db.scalars(select(CaseNote).where(CaseNote.organization_id == principal.organization_id,
        CaseNote.case_id == row.id).order_by(CaseNote.created_at.asc()).limit(500)).all()
    tasks = db.scalars(select(AnalystTask).where(AnalystTask.organization_id == principal.organization_id,
        AnalystTask.case_id == row.id).order_by(AnalystTask.created_at.asc()).limit(200)).all()
    audit_rows = db.scalars(select(AuditLog).where(AuditLog.organization_id == principal.organization_id,
        AuditLog.resource == "case", AuditLog.resource_id == str(row.id))
        .order_by(AuditLog.created_at.asc()).limit(500)).all()
    timeline = [{"type": "created", "resource_id": str(row.id), "label": "Case created", "at": row.created_at}]
    timeline += [{"type": link.resource_type.lower(), "resource_id": link.resource_id,
        "label": link.resource_type.title() + " linked", "at": link.created_at} for link in links]
    timeline += [{"type": "note", "resource_id": str(note.id), "label": note.note, "at": note.created_at} for note in notes]
    timeline += [{"type": "task", "resource_id": str(task.id), "label": task.title, "at": task.created_at} for task in tasks]
    timeline += [{"type": "audit", "resource_id": log.resource_id, "label": log.action,
        "before_state": log.before_state, "after_state": log.after_state, "at": log.created_at} for log in audit_rows]
    timeline.sort(key=lambda item: item["at"])
    return {**_case_view(row), "links": [{"id": str(x.id), "resource_type": x.resource_type,
        "resource_id": x.resource_id, "created_at": x.created_at} for x in links],
        "notes": [{"id": str(x.id), "user_id": str(x.user_id) if x.user_id else None,
            "note": x.note, "created_at": x.created_at} for x in notes],
        "tasks": [_task_view(x) for x in tasks], "timeline": timeline}


@router.post("/cases/{case_id}/links", status_code=201)
def link_case(case_id: str, data: CaseLinkCreate, request: Request,
              principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    cid = _id(case_id, "Case")
    case = db.scalar(select(SecurityCase).where(SecurityCase.id == cid,
        SecurityCase.organization_id == principal.organization_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    models = {"ALERT": Alert, "EVENT": SecurityEvent, "ASSET": Asset, "FINDING": Finding,
        "INCIDENT": Incident, "INVESTIGATION": Investigation, "TASK": AnalystTask, "EVIDENCE": EvidenceMetadata}
    resource_id = _id(data.resource_id, data.resource_type.title())
    resource = db.scalar(select(models[data.resource_type].id).where(models[data.resource_type].id == resource_id,
        models[data.resource_type].organization_id == principal.organization_id))
    if not resource: raise HTTPException(status_code=404, detail=f"{data.resource_type.title()} not found")
    link = CaseResourceLink(organization_id=principal.organization_id, case_id=cid,
        resource_type=data.resource_type, resource_id=str(resource_id))
    db.add(link)
    audit(db, principal, request, "CASE_RESOURCE_LINKED", "case", str(cid),
        {"after_state": {"resource_type": data.resource_type, "resource_id": str(resource_id)}})
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Resource is already linked to this case")
    return {"id": str(link.id), "resource_type": link.resource_type,
        "resource_id": link.resource_id, "created_at": link.created_at}


@router.post("/cases/{case_id}/notes", status_code=201)
def add_case_note(case_id: str, data: CaseNoteCreate, request: Request,
                  principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    cid = _id(case_id, "Case")
    case = db.scalar(select(SecurityCase).where(SecurityCase.id == cid,
        SecurityCase.organization_id == principal.organization_id))
    if not case: raise HTTPException(status_code=404, detail="Case not found")
    note = CaseNote(organization_id=principal.organization_id, case_id=cid,
        user_id=principal.user.id, note=data.note)
    db.add(note)
    audit(db, principal, request, "CASE_NOTE_ADDED", "case", str(cid))
    db.commit()
    return {"id": str(note.id), "note": note.note, "created_at": note.created_at}


@router.patch("/cases/{case_id}")
def update_case(case_id: str, data: CaseUpdate, request: Request,
                principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    cid = _id(case_id, "Case")
    row = db.scalar(select(SecurityCase).where(SecurityCase.id == cid,
        SecurityCase.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Case not found")
    values = data.model_dump(exclude_unset=True)
    if "owner_id" in values: values["owner_id"] = _member(db, principal.organization_id, _id(values["owner_id"], "User"))
    for field, value in values.items(): setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    audit(db, principal, request, "CASE_UPDATED", "case", str(row.id), {"fields": list(values)})
    db.commit()
    return _case_view(row)


@router.get("/tasks")
def list_tasks(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    rows = db.scalars(select(AnalystTask).where(AnalystTask.organization_id == principal.organization_id)
        .order_by(AnalystTask.created_at.desc()).limit(500)).all()
    return [_task_view(row) for row in rows]


@router.post("/tasks", status_code=201)
def create_task(data: TaskCreate, request: Request, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    if not data.investigation_id and not data.case_id:
        raise HTTPException(status_code=422, detail="A task must belong to an investigation or case")
    investigation_id = _id(data.investigation_id, "Investigation")
    case_id = _id(data.case_id, "Case")
    for model, rid, label in ((Investigation, investigation_id, "Investigation"), (SecurityCase, case_id, "Case")):
        if rid and not db.scalar(select(model.id).where(model.id == rid, model.organization_id == principal.organization_id)):
            raise HTTPException(status_code=404, detail=f"{label} not found")
    assignee = _member(db, principal.organization_id, _id(data.assigned_to_id, "User"))
    row = AnalystTask(organization_id=principal.organization_id, investigation_id=investigation_id,
        case_id=case_id, title=data.title, description=data.description, assigned_to_id=assignee,
        priority=data.priority, due_date=data.due_date, created_by_id=principal.user.id)
    db.add(row)
    db.flush()
    notification = _notify_assignee(db, principal.organization_id, assignee, principal.user.id,
        "TASK_ASSIGNED", "Task assigned", row.title, "task", row.id)
    if notification: db.flush()
    audit(db, principal, request, "ANALYST_TASK_CREATED", "task", str(row.id),
        {"after_state": {"title": row.title, "status": row.status, "assigned_to_id": str(assignee) if assignee else None}})
    db.commit()
    _publish_notification(principal.organization_id, assignee, notification.id if notification else None,
        "TASK_ASSIGNED", "Task assigned", "task", row.id)
    return _task_view(row)


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, data: TaskUpdate, request: Request,
                principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    tid = _id(task_id, "Task")
    row = db.scalar(select(AnalystTask).where(AnalystTask.id == tid,
        AnalystTask.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Task not found")
    values = data.model_dump(exclude_unset=True)
    if "assigned_to_id" in values: values["assigned_to_id"] = _member(db, principal.organization_id, _id(values["assigned_to_id"], "User"))
    previous_assignee = row.assigned_to_id
    for field, value in values.items(): setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    notification = None
    if row.assigned_to_id and row.assigned_to_id != previous_assignee:
        notification = _notify_assignee(db, principal.organization_id, row.assigned_to_id,
            principal.user.id, "TASK_ASSIGNED", "Task assigned", row.title, "task", row.id)
        if notification: db.flush()
    audit(db, principal, request, "ANALYST_TASK_UPDATED", "task", str(row.id), {"fields": list(values)})
    db.commit()
    _publish_notification(principal.organization_id, row.assigned_to_id,
        notification.id if notification else None, "TASK_ASSIGNED", "Task assigned", "task", row.id)
    return _task_view(row)


@router.get("/playbooks")
def list_playbooks(principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    rows = db.scalars(select(Playbook).where(Playbook.organization_id == principal.organization_id)
        .order_by(Playbook.created_at.desc()).limit(200)).all()
    return [{"id": str(r.id), "name": r.name, "trigger": r.trigger,
        "steps": r.steps, "enabled": r.enabled, "created_at": r.created_at} for r in rows]


@router.post("/playbooks", status_code=201)
def create_playbook(data: PlaybookCreate, request: Request, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    row = Playbook(organization_id=principal.organization_id, name=data.name,
        trigger=data.trigger, steps=data.steps, enabled=data.enabled)
    db.add(row)
    db.flush()
    audit(db, principal, request, "PLAYBOOK_CREATED", "playbook", str(row.id), {"name": row.name})
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="A playbook with this name already exists")
    return {"id": str(row.id), "name": row.name, "trigger": row.trigger,
        "steps": row.steps, "enabled": row.enabled}


@router.patch("/playbooks/{playbook_id}")
def update_playbook(playbook_id: str, data: PlaybookUpdate, request: Request,
                    principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    pid = _id(playbook_id, "Playbook")
    row = db.scalar(select(Playbook).where(Playbook.id == pid,
        Playbook.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Playbook not found")
    values = data.model_dump(exclude_unset=True)
    before = {"name": row.name, "trigger": row.trigger, "enabled": row.enabled, "steps": row.steps}
    for field, value in values.items(): setattr(row, field, value)
    audit(db, principal, request, "PLAYBOOK_UPDATED", "playbook", str(row.id),
        {"before_state": before, "after_state": {"name": row.name, "trigger": row.trigger,
            "enabled": row.enabled, "steps": row.steps}})
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="A playbook with this name already exists")
    return {"id": str(row.id), "name": row.name, "trigger": row.trigger,
        "steps": row.steps, "enabled": row.enabled}


@router.get("/approvals")
def list_approvals(principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.organization_id == principal.organization_id)
        .order_by(ApprovalRequest.created_at.desc()).limit(200)).all()
    return [{"id": str(r.id), "action_type": r.action_type, "action_payload": r.action_payload,
        "status": r.status, "requested_by_id": str(r.requested_by_id),
        "approved_by_id": str(r.approved_by_id) if r.approved_by_id else None,
        "decision_note": r.decision_note, "execution_result": r.execution_result,
        "created_at": r.created_at, "decided_at": r.decided_at} for r in rows]


@router.post("/approvals", status_code=201)
def create_approval(data: ApprovalCreate, request: Request, principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    supported = {"CONTAINMENT_REVIEW", "CREATE_TASK", "SET_ALERT_STATUS", "CREATE_INCIDENT"}
    if data.action_type not in supported:
        raise HTTPException(status_code=422, detail="Unsupported action type; this platform executes only approved internal task, alert-status, or incident workflows")
    try:
        if data.action_type == "CREATE_TASK": TaskCreate.model_validate(data.action_payload)
        elif data.action_type == "SET_ALERT_STATUS":
            if set(data.action_payload) != {"alert_id", "status"}: raise ValueError("Expected alert_id and status only")
            AlertUpdate.model_validate({"status": data.action_payload["status"]})
            _id(str(data.action_payload["alert_id"]), "Alert")
        elif data.action_type == "CREATE_INCIDENT": IncidentCreate.model_validate(data.action_payload)
    except (ValidationError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=f"Invalid approved-action payload: {error.__class__.__name__}")
    row = ApprovalRequest(organization_id=principal.organization_id,
        requested_by_id=principal.user.id, action_type=data.action_type,
        action_payload=data.action_payload, status="PENDING")
    db.add(row)
    db.flush()
    audit(db, principal, request, "APPROVAL_REQUESTED", "approval", str(row.id), {"action_type": row.action_type})
    db.commit()
    return {"id": str(row.id), "status": row.status,
        "note": "Approval requests are stored for manager review; only the documented internal actions are executable after approval."}


@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, data: ApprovalDecision, request: Request,
                    principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    aid = _id(approval_id, "Approval")
    row = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == aid,
        ApprovalRequest.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Approval request not found")
    if row.status != "PENDING": raise HTTPException(status_code=409, detail="Approval is already decided")
    execution = {"executed": False, "reason": "review_record_only"}
    if data.status == "APPROVED":
        payload = row.action_payload or {}
        if row.action_type in {"CREATE_TASK", "SET_ALERT_STATUS", "CREATE_INCIDENT"} and row.requested_by_id == principal.user.id:
            raise HTTPException(status_code=403, detail="A different manager must approve this executable action")
        if row.action_type == "CREATE_TASK":
            try: task_data = TaskCreate.model_validate(payload)
            except ValidationError: raise HTTPException(status_code=422, detail="Approved task payload is invalid")
            if not task_data.investigation_id and not task_data.case_id:
                raise HTTPException(status_code=422, detail="Approved task must belong to an investigation or case")
            investigation_id, case_id = _id(task_data.investigation_id, "Investigation"), _id(task_data.case_id, "Case")
            for model, rid, label in ((Investigation, investigation_id, "Investigation"), (SecurityCase, case_id, "Case")):
                if rid and not db.scalar(select(model.id).where(model.id == rid, model.organization_id == principal.organization_id)):
                    raise HTTPException(status_code=404, detail=f"{label} not found")
            assignee = _member(db, principal.organization_id, _id(task_data.assigned_to_id, "User"))
            task = AnalystTask(organization_id=principal.organization_id, investigation_id=investigation_id,
                case_id=case_id, title=task_data.title, description=task_data.description,
                assigned_to_id=assignee, priority=task_data.priority, due_date=task_data.due_date,
                created_by_id=principal.user.id)
            db.add(task)
            db.flush()
            notification = _notify_assignee(db, principal.organization_id, assignee, principal.user.id,
                "TASK_ASSIGNED", "Approved task assigned", task.title, "task", task.id)
            if notification: db.flush()
            audit(db, principal, request, "APPROVED_TASK_CREATED", "task", str(task.id),
                {"after_state": {"title": task.title, "priority": task.priority}})
            execution = {"executed": True, "resource_type": "task", "resource_id": str(task.id)}
            _publish_notification(principal.organization_id, assignee, notification.id if notification else None,
                "TASK_ASSIGNED", "Approved task assigned", "task", task.id)
        elif row.action_type == "SET_ALERT_STATUS":
            if set(payload) != {"alert_id", "status"}: raise HTTPException(status_code=422, detail="Invalid alert action payload")
            try: update = AlertUpdate.model_validate({"status": payload["status"]})
            except ValidationError: raise HTTPException(status_code=422, detail="Invalid alert status")
            alert_id = _id(str(payload["alert_id"]), "Alert")
            alert = db.scalar(select(Alert).where(Alert.id == alert_id,
                Alert.organization_id == principal.organization_id))
            if not alert: raise HTTPException(status_code=404, detail="Alert not found")
            before = alert.status
            alert.status = update.status
            if update.status == "RESOLVED": alert.resolved_at = datetime.now(timezone.utc)
            elif update.status != "FALSE_POSITIVE": alert.resolved_at = None
            audit(db, principal, request, "APPROVED_ALERT_STATUS_CHANGED", "alert", str(alert.id),
                {"before_state": {"status": before}, "after_state": {"status": alert.status}})
            execution = {"executed": True, "resource_type": "alert", "resource_id": str(alert.id), "status": alert.status}
        elif row.action_type == "CREATE_INCIDENT":
            try: incident_data = IncidentCreate.model_validate(payload)
            except ValidationError: raise HTTPException(status_code=422, detail="Approved incident payload is invalid")
            incident = Incident(organization_id=principal.organization_id, **incident_data.model_dump())
            db.add(incident)
            db.flush()
            db.add(SecurityEvent(organization_id=principal.organization_id, event_type="INCIDENT_CREATED",
                severity=incident.severity, message=incident.title, metadata_json={"incident_id": str(incident.id)}))
            from app.services.webhooks import create_delivery_rows
            create_delivery_rows(db, principal.organization_id, "INCIDENT_CREATED", {
                "type": "INCIDENT_CREATED", "organization_id": str(principal.organization_id),
                "incident_id": str(incident.id), "title": incident.title,
                "severity": incident.severity, "status": incident.status})
            execution = {"executed": True, "resource_type": "incident", "resource_id": str(incident.id)}
        elif row.action_type != "CONTAINMENT_REVIEW":
            raise HTTPException(status_code=422, detail="This action type has no approved executor")
    row.status = data.status
    row.approved_by_id = principal.user.id
    row.decision_note = data.note
    row.execution_result = execution
    row.decided_at = datetime.now(timezone.utc)
    audit(db, principal, request, "APPROVAL_DECIDED", "approval", str(row.id),
        {"after_state": {"status": row.status, "action_type": row.action_type, "execution_result": execution}})
    db.commit()
    return {"id": str(row.id), "status": row.status, "decided_at": row.decided_at,
        "execution_result": execution,
        "note": "Only approved internal task, alert-status, and incident actions execute. No shell, network, containment, or third-party system action is executed."}
