import hashlib
from tests.conftest import csrf


def test_evidence_upload_hash_download_and_tenant_scope(client, owner, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "evidence_storage_path", str(tmp_path))
    created = client.post("/api/investigations", headers=csrf(client), json={"title": "Evidence review"})
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]
    content = b"sample forensic artifact\x00\x01"
    uploaded = client.post(f"/api/investigations/{investigation_id}/evidence", headers=csrf(client),
        data={"notes": "Collected for a controlled review"}, files={"file": ("../../proof.bin", content, "application/octet-stream")})
    assert uploaded.status_code == 201, uploaded.text
    evidence = uploaded.json()
    assert evidence["filename"] == "proof.bin"
    assert evidence["sha256"] == hashlib.sha256(content).hexdigest()
    download = client.get(f"/api/investigations/{investigation_id}/evidence/{evidence['id']}")
    assert download.status_code == 200 and download.content == content
    assert "attachment" in download.headers["content-disposition"]
    assert client.get(f"/api/investigations/00000000-0000-0000-0000-000000000001/evidence/{evidence['id']}").status_code == 404


def test_evidence_rejects_empty_and_oversized_uploads(client, owner, monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "evidence_storage_path", str(tmp_path))
    investigation_id = client.post("/api/investigations", headers=csrf(client), json={"title": "Evidence limits"}).json()["id"]
    empty = client.post(f"/api/investigations/{investigation_id}/evidence", headers=csrf(client),
        files={"file": ("empty.bin", b"", "application/octet-stream")})
    assert empty.status_code == 422
    too_large = client.post(f"/api/investigations/{investigation_id}/evidence", headers=csrf(client),
        files={"file": ("large.bin", b"x" * (10 * 1024 * 1024 + 1), "application/octet-stream")})
    assert too_large.status_code == 413
