import os
import tempfile
from pathlib import Path

_db = Path(tempfile.gettempdir()) / f"cybershield-test-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["JWT_SECRET"] = "test-only-secret-with-more-than-32-characters"
os.environ["APP_URL"] = "http://testserver"
os.environ["ENVIRONMENT"] = "development"
os.environ["COOKIE_SECURE"] = "false"

import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine
from app.main import app
from app.routes import auth

@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    auth._attempts.clear()
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def owner(client):
    r = client.post("/api/auth/register", json={"email":"owner@example.com", "full_name":"Org Owner",
        "password":"a-secure-password-123", "organization_name":"Test Organization"})
    assert r.status_code == 201, r.text
    return r.json()

def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
