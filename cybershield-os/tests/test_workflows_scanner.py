import pytest
from tests.conftest import csrf
from app.services.scanner import _validate_host
from app.services import scanner


def test_risk_incident_and_report_pdf(client, owner):
    risk = client.post("/api/risks", headers=csrf(client), json={"title":"Backups may be exposed", "description":"Review remote backup ACLs", "likelihood":4, "impact":5, "treatment":"MITIGATE"})
    assert risk.status_code == 201 and risk.json()["risk_score"] == 20
    incident = client.post("/api/incidents", headers=csrf(client), json={"title":"Suspicious sign-in", "severity":"HIGH", "description":"Unusual login anomaly"})
    assert incident.status_code == 201
    assert client.get("/api/incidents").json()[0]["title"] == "Suspicious sign-in"
    created = client.post("/api/reports", headers=csrf(client), json={"report_type":"EXECUTIVE"})
    assert created.status_code == 201, created.text
    listed = client.get("/api/reports")
    assert listed.status_code == 200 and len(listed.json()) == 1
    pdf = client.get(f"/api/reports/{created.json()['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert client.get("/api/audit-logs").status_code == 200


def test_scanner_rejects_private_and_local_targets():
    for host in ["127.0.0.1", "10.0.0.2", "localhost", "169.254.169.254"]:
        with pytest.raises(ValueError):
            _validate_host(host)
    with pytest.raises(ValueError):
        _validate_host("https://example.com/admin")
    for host in ["good.example.com\r\nX-Injected: yes", "example.com#fragment", "bad..example.com", "service.internal"]:
        with pytest.raises(ValueError):
            _validate_host(host)
    assert _validate_host("93.184.216.34") == "93.184.216.34"


def test_scanner_rejects_dns_rebinding_to_private_ip(monkeypatch):
    record = (2, 1, 6, "", ("127.0.0.1", 443))
    monkeypatch.setattr(scanner.socket, "getaddrinfo", lambda *args, **kwargs: [record])
    with pytest.raises(ValueError, match="blocked"):
        scanner._resolve_public("public.example.com")


def test_risk_management_updates_treatment_and_score(client, owner):
    risk = client.post("/api/risks", headers=csrf(client), json={
        "title":"Unpatched device", "description":"Test risk record", "likelihood":5, "impact":5,
        "treatment":"MITIGATE", "owner":"Security team"})
    assert risk.status_code == 201, risk.text
    before = client.get("/api/dashboard").json()["security_score"]
    updated = client.patch(f"/api/risks/{risk.json()['id']}", headers=csrf(client),
        json={"status":"CLOSED", "treatment":"ACCEPT"})
    assert updated.status_code == 200 and updated.json()["status"] == "CLOSED"
    assert client.get("/api/dashboard").json()["security_score"] > before


def test_worker_ignores_missing_scan_without_network(client):
    from services.worker.tasks import scan_asset
    result = scan_asset.run("00000000-0000-0000-0000-000000000000")
    assert result == {"status": "cancelled"}
