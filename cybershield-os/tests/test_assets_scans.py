from app.db import SessionLocal
from app.models import Asset
from sqlalchemy import select
from tests.conftest import csrf
from uuid import UUID


def register(client, email, org):
    return client.post("/api/auth/register", json={"email":email, "full_name":"Test User",
        "password":"safe-password-for-test-123", "organization_name":org}).json()


def test_asset_authorization_and_scan_queue(client, owner, monkeypatch):
    created = client.post("/api/assets", headers=csrf(client), json={"name":"Public docs", "type":"WEBSITE", "hostname":"docs.example.com"})
    assert created.status_code == 201, created.text
    asset = created.json()
    denied = client.post(f"/api/assets/{asset['id']}/scans", headers=csrf(client))
    assert denied.status_code == 403
    missing_confirm = client.post(f"/api/assets/{asset['id']}/authorize", headers=csrf(client),
        json={"confirmed":False, "statement":"I have permission from my employer to run checks."})
    assert missing_confirm.status_code == 400
    authorized = client.post(f"/api/assets/{asset['id']}/authorize", headers=csrf(client),
        json={"confirmed":True, "statement":"I am the authorized owner of this organization domain."})
    assert authorized.status_code == 200 and authorized.json()["authorization_status"] == "AUTHORIZED"
    from services.worker.tasks import scan_asset
    monkeypatch.setattr(scan_asset, "delay", lambda scan_id: None)
    queued = client.post(f"/api/assets/{asset['id']}/scans", headers=csrf(client))
    assert queued.status_code == 202, queued.text
    scans = client.get("/api/scans").json()
    assert scans[0]["id"] == queued.json()["id"] and scans[0]["status"] == "QUEUED"
    assert client.get(f"/api/scans/{queued.json()['id']}").status_code == 200


def test_organization_isolation_returns_not_found(client):
    first = register(client, "a@example.com", "Org A")
    created = client.post("/api/assets", headers=csrf(client), json={"name":"A site", "hostname":"a.example.com"})
    asset_id = created.json()["id"]
    client.post("/api/auth/logout", headers=csrf(client))
    client.cookies.clear()
    second = register(client, "b@example.com", "Org B")
    assert second["organization"]["id"] != first["organization"]["id"]
    assert client.get("/api/assets").json() == []
    assert client.get(f"/api/assets/{asset_id}").status_code == 404
    assert client.get("/api/dashboard").json()["assets"] == 0


def test_findings_change_score_and_remain_org_scoped(client, owner):
    asset = client.post("/api/assets", headers=csrf(client), json={"name":"Score site", "hostname":"score.example.com"}).json()
    with SessionLocal() as db:
        from app.models import Finding
        db.add(Finding(organization_id=UUID(owner["organization"]["id"]), asset_id=UUID(asset["id"]), title="Critical issue",
                       description="Evidence from a scan", severity="CRITICAL", category="TLS", evidence={}, remediation="Fix TLS", status="OPEN"))
        db.commit()
    before = client.get("/api/dashboard").json()["security_score"]
    finding = client.get("/api/findings").json()[0]
    assert client.get(f"/api/findings/{finding['id']}").status_code == 200
    assert client.get("/api/vulnerabilities").json()[0]["id"] == finding["id"]
    updated = client.patch(f"/api/findings/{finding['id']}", headers=csrf(client), json={"status":"RESOLVED"})
    assert updated.status_code == 200 and updated.json()["security_score"] > before


def test_asset_update_does_not_retarget_authorized_host_and_delete_is_scoped(client, owner):
    asset = client.post("/api/assets", headers=csrf(client), json={"name":"Before", "hostname":"before.example.com"}).json()
    response = client.patch(f"/api/assets/{asset['id']}", headers=csrf(client), json={"name":"After"})
    assert response.status_code == 200 and response.json()["hostname"] == "before.example.com"
    forbidden_retarget = client.patch(f"/api/assets/{asset['id']}", headers=csrf(client), json={"hostname":"other.example.com"})
    assert forbidden_retarget.status_code == 422
    deleted = client.delete(f"/api/assets/{asset['id']}", headers=csrf(client))
    assert deleted.status_code == 204
    assert client.get(f"/api/assets/{asset['id']}").status_code == 404
