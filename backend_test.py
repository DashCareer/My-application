"""DashCareer backend API tests using pytest"""
import os
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://app-dashboard-pro-3.preview.emergentagent.com').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="session")
def test_session(mongo_db):
    ts = int(datetime.now().timestamp() * 1000)
    user_id = f"TEST_user_{ts}"
    token = f"TEST_session_{ts}"
    mongo_db.users.insert_one({
        "user_id": user_id, "email": f"TEST_qa{ts}@dash.test", "name": "TEST QA",
        "picture": "", "plan": "free",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"user_id": user_id, "token": token}
    mongo_db.applications.delete_many({"user_id": user_id})
    mongo_db.documents.delete_many({"user_id": user_id})
    mongo_db.ai_usage.delete_many({"user_id": user_id})
    mongo_db.user_sessions.delete_many({"user_id": user_id})
    mongo_db.users.delete_many({"user_id": user_id})


@pytest.fixture
def auth_client(test_session):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {test_session['token']}",
    })
    return s


# --- Root ---
def test_root():
    r = requests.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    assert "DashCareer" in r.json().get("message", "")


# --- Auth ---
def test_auth_me_no_token():
    r = requests.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 401


def test_auth_me_with_token(auth_client, test_session):
    r = auth_client.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == test_session["user_id"]
    assert data["plan"] == "free"


def test_auth_session_invalid():
    r = requests.post(f"{BASE_URL}/api/auth/session", json={"session_id": "bogus_id_123"})
    assert r.status_code in (400, 401)


# --- Applications CRUD ---
def test_applications_crud(auth_client):
    # Create
    r = auth_client.post(f"{BASE_URL}/api/applications",
                         json={"company": "TEST_Acme", "role": "PM", "status": "applied"})
    assert r.status_code == 200, r.text
    app = r.json()
    assert app["company"] == "TEST_Acme"
    assert "id" in app
    app_id = app["id"]

    # List - verify persistence
    r = auth_client.get(f"{BASE_URL}/api/applications")
    assert r.status_code == 200
    assert any(a["id"] == app_id for a in r.json())

    # Update
    r = auth_client.patch(f"{BASE_URL}/api/applications/{app_id}", json={"status": "interview"})
    assert r.status_code == 200
    assert r.json()["status"] == "interview"

    # Verify update
    r = auth_client.get(f"{BASE_URL}/api/applications")
    assert next(a for a in r.json() if a["id"] == app_id)["status"] == "interview"

    # Delete
    r = auth_client.delete(f"{BASE_URL}/api/applications/{app_id}")
    assert r.status_code == 200
    r = auth_client.delete(f"{BASE_URL}/api/applications/{app_id}")
    assert r.status_code == 404


def test_applications_requires_auth():
    r = requests.get(f"{BASE_URL}/api/applications")
    assert r.status_code == 401


# --- Documents CRUD ---
def test_documents_crud(auth_client):
    r = auth_client.post(f"{BASE_URL}/api/documents",
                         json={"title": "TEST_Resume", "type": "resume", "content": "Hello"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["type"] == "resume"
    doc_id = doc["id"]

    r = auth_client.get(f"{BASE_URL}/api/documents")
    assert r.status_code == 200
    assert any(d["id"] == doc_id for d in r.json())

    r = auth_client.delete(f"{BASE_URL}/api/documents/{doc_id}")
    assert r.status_code == 200


# --- Analytics ---
def test_analytics_overview(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/analytics/overview")
    assert r.status_code == 200
    data = r.json()
    for k in ["total", "by_status", "response_rate", "ai_used_today", "plan"]:
        assert k in data
    for s in ["applied", "interview", "accepted", "rejected"]:
        assert s in data["by_status"]


# --- AI Tools (real Claude calls) ---
def test_ai_optimize_resume(auth_client):
    r = auth_client.post(f"{BASE_URL}/api/ai/optimize-resume",
                         json={"resume": "John Doe, SWE 3yrs Python", "job_description": "Backend role"},
                         timeout=60)
    assert r.status_code == 200, r.text
    assert len(r.json().get("result", "")) > 20


def test_ai_suggestions(auth_client):
    r = auth_client.post(f"{BASE_URL}/api/ai/suggestions",
                         json={"role": "Backend Engineer", "skills": "Python, FastAPI"},
                         timeout=60)
    assert r.status_code == 200, r.text
    assert len(r.json().get("result", "")) > 20


# --- Free plan limit (apps=10) ---
def test_free_plan_app_limit(mongo_db):
    ts = int(datetime.now().timestamp() * 1000)
    user_id = f"TEST_limit_{ts}"
    token = f"TEST_limit_tok_{ts}"
    mongo_db.users.insert_one({"user_id": user_id, "email": f"TEST_lim{ts}@d.test",
                               "name": "L", "picture": "", "plan": "free",
                               "created_at": datetime.now(timezone.utc).isoformat()})
    mongo_db.user_sessions.insert_one({"user_id": user_id, "session_token": token,
        "expires_at": (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()})
    try:
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        for i in range(10):
            r = requests.post(f"{BASE_URL}/api/applications", headers=h,
                              json={"company": f"TEST_C{i}", "role": "X"})
            assert r.status_code == 200
        r = requests.post(f"{BASE_URL}/api/applications", headers=h,
                          json={"company": "TEST_overflow", "role": "X"})
        assert r.status_code == 403
    finally:
        mongo_db.applications.delete_many({"user_id": user_id})
        mongo_db.user_sessions.delete_many({"user_id": user_id})
        mongo_db.users.delete_many({"user_id": user_id})
