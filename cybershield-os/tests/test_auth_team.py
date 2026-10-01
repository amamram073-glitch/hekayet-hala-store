from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Membership, User
from tests.conftest import csrf


def test_register_login_me_and_logout(client):
    data = client.post("/api/auth/register", json={"email":"first@example.com", "full_name":"First Person",
        "password":"strong-test-password-123", "organization_name":"First Org"})
    assert data.status_code == 201
    assert client.cookies.get("cyber_session")
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["organization"]["name"] == "First Org"
    assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    login = client.post("/api/auth/login", json={"email":"first@example.com", "password":"strong-test-password-123"})
    assert login.status_code == 200
    assert client.get("/api/auth/sessions").status_code == 200


def test_mutating_request_requires_csrf(client, owner):
    r = client.post("/api/assets", json={"name":"example", "hostname":"example.com"})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_invitation_is_single_use_and_assigns_role(client, owner):
    created = client.post("/api/team/invitations", headers=csrf(client), json={"email":"analyst@example.com", "role":"SECURITY_ANALYST"})
    assert created.status_code == 201, created.text
    token = created.json()["invite_url"].split("token=", 1)[1]
    accepted = client.post("/api/team/accept-invitation", headers=csrf(client), json={
        "token":token, "full_name":"New Analyst", "password":"new-analyst-password-123"})
    assert accepted.status_code == 201, accepted.text
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "analyst@example.com"))
        member = db.scalar(select(Membership).where(Membership.user_id == user.id))
        assert member.role == "SECURITY_ANALYST"
    client.cookies.clear()
    replay = client.post("/api/team/accept-invitation", json={"token":token, "full_name":"Replay", "password":"new-analyst-password-456"})
    assert replay.status_code == 400


def test_team_endpoints_enforce_role(client, owner):
    with SessionLocal() as db:
        membership = db.scalar(select(Membership).where(Membership.organization_id == UUID(owner["organization"]["id"])))
        membership.role = "VIEWER"
        db.commit()
    response = client.post("/api/team/invitations", headers=csrf(client), json={"email":"x@example.com", "role":"VIEWER"})
    assert response.status_code == 403


def test_session_revocation_and_password_rotation(client):
    email = "rotate@example.com"
    old_password = "current-secure-password-123"
    new_password = "replacement-secure-password-456"
    first = client.post("/api/auth/register", json={"email":email, "full_name":"Password User",
        "password":old_password, "organization_name":"Password Org"})
    assert first.status_code == 201
    first_session_id = client.get("/api/auth/sessions").json()[0]["id"]
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email":email, "password":old_password}).status_code == 200
    assert len(client.get("/api/auth/sessions").json()) == 2
    revoked = client.delete(f"/api/auth/sessions/{first_session_id}", headers=csrf(client))
    assert revoked.status_code == 204
    changed = client.post("/api/auth/change-password", headers=csrf(client), json={
        "current_password":old_password, "new_password":new_password})
    assert changed.status_code == 200 and changed.json()["revoked_other_sessions"] == 0
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email":email, "password":old_password}).status_code == 401
    assert client.post("/api/auth/login", json={"email":email, "password":new_password}).status_code == 200
