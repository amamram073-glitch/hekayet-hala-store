from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Alert, ApiKey, Investigation, SecurityEvent, ThreatIndicator
from tests.conftest import csrf


def register(client, email, org):
    return client.post("/api/auth/register", json={"email": email, "full_name": "SOC Analyst",
        "password": "safe-password-for-test-123", "organization_name": org}, headers=csrf(client)).json()


def new_key(client):
    res = client.post("/api/api-keys", headers=csrf(client), json={
        "name": "CI event source", "permissions": ["EVENT_INGEST"]})
    assert res.status_code == 201, res.text
    return res.json()


def ingest(client, token, **overrides):
    body = {"source": "Identity Gateway", "source_type": "AUTHENTICATION",
        "event_type": "AUTH_FAILURE", "severity": "MEDIUM", "username": "analyst@example.com",
        "ip_address": "198.51.100.20", "message": "Authentication failed", "metadata": {}}
    body.update(overrides)
    return client.post("/api/events/ingest", headers={"Authorization": f"Bearer {token}"}, json=body)


def test_api_key_creation_rotation_and_revocation_are_scoped(client, owner):
    created = new_key(client)
    assert created["api_key"].startswith("cso_")
    assert "token_hash" not in created
    assert client.get("/api/api-keys").json()[0]["key_prefix"] == created["key_prefix"]
    old_ingest = ingest(client, created["api_key"])
    assert old_ingest.status_code == 202, old_ingest.text
    rotated = client.post(f"/api/api-keys/{created['id']}/rotate", headers=csrf(client))
    assert rotated.status_code == 201, rotated.text
    assert ingest(client, created["api_key"]).status_code == 401
    assert ingest(client, rotated.json()["api_key"]).status_code == 202
    assert client.delete(f"/api/api-keys/{rotated.json()['id']}", headers=csrf(client)).status_code == 204
    assert ingest(client, rotated.json()["api_key"]).status_code == 401


def test_ingestion_rejects_client_tenant_and_normalizes_event(client, owner, monkeypatch):
    key = new_key(client)
    from services.worker.tasks import process_security_event
    monkeypatch.setattr(process_security_event, "delay", lambda event_id: None)
    response = ingest(client, key["api_key"], organization_id="00000000-0000-0000-0000-000000000000",
                      event_type="auth_failure", hostname="EXAMPLE.COM.")
    assert response.status_code == 422
    response = ingest(client, key["api_key"], event_type="auth_failure", hostname="EXAMPLE.COM.")
    assert response.status_code == 202, response.text
    with SessionLocal() as db:
        event = db.get(SecurityEvent, UUID(response.json()["id"]))
        assert event.organization_id == UUID(owner["organization"]["id"])
        assert event.event_type == "AUTH_FAILURE" and event.hostname == "example.com"
        assert event.processing_status == "QUEUED"
    assert ingest(client, key["api_key"], ip_address="127.0.0.1x").status_code == 422


def test_rule_engine_generates_explained_alert_and_links_evidence(client, owner, monkeypatch):
    key = new_key(client)
    rule = client.post("/api/detection-rules", headers=csrf(client), json={
        "name": "Repeated auth failures", "description": "Multiple login denials",
        "severity": "HIGH", "conditions": [{"field": "event_type", "operator": "eq", "value": "AUTH_FAILURE"}],
        "match_count": 3, "window_minutes": 10})
    assert rule.status_code == 200 or rule.status_code == 201, rule.text
    from services.worker.tasks import process_security_event
    monkeypatch.setattr(process_security_event, "delay", lambda event_id: None)
    ids = []
    for _ in range(3):
        response = ingest(client, key["api_key"])
        assert response.status_code == 202, response.text
        ids.append(response.json()["id"])
        result = process_security_event(response.json()["id"])
        assert result["status"] == "processed", result
    alerts = client.get("/api/alerts?severity=HIGH").json()
    target = next(a for a in alerts["items"] if a["title"] == "Repeated auth failures")
    detail = client.get(f"/api/alerts/{target['id']}").json()
    assert len(detail["events"]) == 3
    assert detail["reason"].startswith("Rule matched 3")
    assert detail["recommendation"]


def test_indicators_create_and_match_only_within_organization(client, owner, monkeypatch):
    indicator = client.post("/api/indicators", headers=csrf(client), json={
        "type": "IP", "value": "198.51.100.20", "confidence": 88, "source": "Internal feed"})
    assert indicator.status_code == 201, indicator.text
    key = new_key(client)
    from services.worker.tasks import process_security_event
    monkeypatch.setattr(process_security_event, "delay", lambda event_id: None)
    event = ingest(client, key["api_key"])
    assert event.status_code == 202
    processed = process_security_event(event.json()["id"])
    assert processed["alerts"] == 1
    alerts = client.get("/api/alerts?q=indicator").json()["items"]
    assert any(a["title"] == "Threat indicator match: IP" for a in alerts)
    register(client, "other@example.com", "Other SOC")
    assert client.get("/api/indicators").json() == []
    assert client.get(f"/api/alerts/{alerts[0]['id']}").status_code == 404


def test_investigation_case_task_and_approval_workflows(client, owner):
    created = client.post("/api/investigations", headers=csrf(client), json={
        "title": "Review suspicious sign-ins", "description": "Investigate an event sequence", "priority": "HIGH"})
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]
    note = client.post(f"/api/investigations/{investigation_id}/notes", headers=csrf(client),
        json={"note": "Validated the source address with the identity owner."})
    assert note.status_code == 201
    task = client.post("/api/tasks", headers=csrf(client), json={
        "title": "Confirm account owner", "investigation_id": investigation_id})
    assert task.status_code == 201, task.text
    assert client.patch(f"/api/tasks/{task.json()['id']}", headers=csrf(client),
        json={"status": "DONE"}).json()["status"] == "DONE"
    case = client.post("/api/cases", headers=csrf(client), json={"title": "Identity investigation", "priority": "HIGH"})
    assert case.status_code == 201 and case.json()["case_number"].startswith("CS-")
    assert client.patch(f"/api/cases/{case.json()['id']}", headers=csrf(client),
        json={"status": "IN_PROGRESS"}).json()["status"] == "IN_PROGRESS"
    approval = client.post("/api/approvals", headers=csrf(client), json={
        "action_type": "CONTAINMENT_REVIEW", "action_payload": {"scope": "single account"}})
    assert approval.status_code == 201
    decided = client.post(f"/api/approvals/{approval.json()['id']}/decision", headers=csrf(client),
        json={"status": "APPROVED", "note": "Review recorded"})
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED"
    detail = client.get(f"/api/investigations/{investigation_id}").json()
    assert any(x["type"] == "note" for x in detail["timeline"])
    assert any(x["type"] == "task" for x in detail["timeline"])


def test_soc_metrics_and_search_use_real_org_records(client, owner):
    key = new_key(client)
    response = ingest(client, key["api_key"], event_type="PRIVILEGED_ACCOUNT_ACTIVITY",
        message="Admin change requires review")
    assert response.status_code == 202
    overview = client.get("/api/soc/overview").json()
    assert overview["events_24h"] >= 1
    assert overview["assets_under_monitoring"] == 0
    search = client.get("/api/search?q=Admin").json()
    assert "events" in search and search["events"]
    assert client.get("/api/security-center").json()["checks"]
    assert "nodes" in client.get("/api/soc/risk-graph").json()



def test_executable_approval_requires_a_different_manager(client, owner):
    investigation = client.post("/api/investigations", headers=csrf(client), json={
        "title": "Independent approval target", "priority": "MEDIUM"})
    assert investigation.status_code == 201
    request = client.post("/api/approvals", headers=csrf(client), json={
        "action_type": "CREATE_TASK", "action_payload": {
            "title": "Approved follow-up", "investigation_id": investigation.json()["id"],
            "priority": "HIGH"}})
    assert request.status_code == 201, request.text
    decision = client.post(f"/api/approvals/{request.json()['id']}/decision", headers=csrf(client), json={
        "status": "APPROVED", "note": "Self-approval must not execute"})
    assert decision.status_code == 403
    row = next(x for x in client.get("/api/approvals").json() if x["id"] == request.json()["id"])
    assert row["status"] == "PENDING"
    tasks = client.get(f"/api/investigations/{investigation.json()['id']}").json()["tasks"]
    assert all(x["title"] != "Approved follow-up" for x in tasks)


def test_metrics_report_insufficient_data_instead_of_estimates(client, owner):
    result = client.get("/api/soc/metrics?period=24h")
    assert result.status_code == 200
    metrics = result.json()
    assert metrics["mttd"] == {"value_seconds": None, "sample_count": 0, "status": "INSUFFICIENT_DATA"}
    assert metrics["mttr"]["status"] == "INSUFFICIENT_DATA"
    assert metrics["false_positive_rate"] is None
