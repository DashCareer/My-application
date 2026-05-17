"""DashCareer iteration 2 tests: Pro-only AI endpoints (cv-rewrite, interview-prep, jd-scanner)
plus re-verify DELETE /api/account and POST /api/reviews Pro-gating."""
import os
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://app-dashboard-pro-3.preview.emergentagent.com').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

SHORT_RESUME = "Jane Doe — Frontend Engineer. 5 yrs React, TypeScript, Next.js. Built design systems at Acme. BSc CS."
SHORT_JD = "Senior Frontend Engineer. React, TS, Next.js, accessibility, design systems."


@pytest.fixture(scope="module")
def mongo_db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _seed_user(db, plan):
    ts = int(datetime.now().timestamp() * 1000000)
    uid = f"TEST_it2_{plan}_{ts}"
    tok = f"TEST_it2_session_{plan}_{ts}"
    db.users.insert_one({
        "user_id": uid, "email": f"TEST_it2_{plan}_{ts}@dash.test",
        "name": f"TEST {plan}", "picture": "", "plan": plan,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.user_sessions.insert_one({
        "user_id": uid, "session_token": tok,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid, tok


def _cleanup(db, uid):
    db.applications.delete_many({"user_id": uid})
    db.documents.delete_many({"user_id": uid})
    db.ai_usage.delete_many({"user_id": uid})
    db.reviews.delete_many({"user_id": uid})
    db.user_sessions.delete_many({"user_id": uid})
    db.users.delete_many({"user_id": uid})


@pytest.fixture(scope="module")
def free_session(mongo_db):
    uid, tok = _seed_user(mongo_db, "free")
    yield {"user_id": uid, "token": tok}
    _cleanup(mongo_db, uid)


@pytest.fixture(scope="module")
def pro_session(mongo_db):
    uid, tok = _seed_user(mongo_db, "pro")
    yield {"user_id": uid, "token": tok}
    _cleanup(mongo_db, uid)


def _client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


# ============ 401 without auth ============
@pytest.mark.parametrize("path", ["/api/ai/cv-rewrite", "/api/ai/interview-prep", "/api/ai/jd-scanner"])
def test_pro_endpoints_require_auth(path):
    r = requests.post(f"{BASE_URL}{path}", json={})
    assert r.status_code == 401, f"{path} expected 401 got {r.status_code}"


# ============ 403 for free users ============
def test_cv_rewrite_blocks_free_user(free_session):
    r = _client(free_session["token"]).post(
        f"{BASE_URL}/api/ai/cv-rewrite",
        json={"resume": SHORT_RESUME, "target_role": "Senior Frontend Engineer"},
    )
    assert r.status_code == 403
    detail = r.json().get("detail", "")
    assert "Pro" in detail and ("£7" in detail or "Upgrade" in detail), f"unexpected detail: {detail}"


def test_interview_prep_blocks_free_user(free_session):
    r = _client(free_session["token"]).post(
        f"{BASE_URL}/api/ai/interview-prep",
        json={"role": "Senior Backend Engineer"},
    )
    assert r.status_code == 403
    assert "Pro" in r.json().get("detail", "")


def test_jd_scanner_blocks_free_user(free_session):
    r = _client(free_session["token"]).post(
        f"{BASE_URL}/api/ai/jd-scanner",
        json={"resume": SHORT_RESUME, "job_description": SHORT_JD},
    )
    assert r.status_code == 403
    assert "Pro" in r.json().get("detail", "")


# ============ JD scanner empty job_description validation (Pro user, 400) ============
def test_jd_scanner_validates_empty_jd(pro_session):
    r = _client(pro_session["token"]).post(
        f"{BASE_URL}/api/ai/jd-scanner",
        json={"resume": SHORT_RESUME, "job_description": "   "},
    )
    assert r.status_code == 400
    assert "Job description" in r.json().get("detail", "")


# ============ Pro user can hit endpoints + AI usage logged ============
def test_cv_rewrite_pro_success_and_logs_usage(pro_session, mongo_db):
    r = _client(pro_session["token"]).post(
        f"{BASE_URL}/api/ai/cv-rewrite",
        json={"resume": SHORT_RESUME, "target_role": "Senior Frontend Engineer"},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data
    assert isinstance(data["result"], str) and len(data["result"]) > 50
    # Markdown sections expected (some headings)
    assert "##" in data["result"]
    # ai_usage logged
    cnt = mongo_db.ai_usage.count_documents({"user_id": pro_session["user_id"], "kind": "cv_rewrite"})
    assert cnt >= 1


def test_interview_prep_pro_success_and_logs_usage(pro_session, mongo_db):
    r = _client(pro_session["token"]).post(
        f"{BASE_URL}/api/ai/interview-prep",
        json={"role": "Senior Backend Engineer", "job_description": SHORT_JD},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data and len(data["result"]) > 50
    assert "##" in data["result"]
    cnt = mongo_db.ai_usage.count_documents({"user_id": pro_session["user_id"], "kind": "interview_prep"})
    assert cnt >= 1


def test_jd_scanner_pro_success_and_logs_usage(pro_session, mongo_db):
    r = _client(pro_session["token"]).post(
        f"{BASE_URL}/api/ai/jd-scanner",
        json={"resume": SHORT_RESUME, "job_description": SHORT_JD},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "result" in data and len(data["result"]) > 50
    assert "##" in data["result"]
    cnt = mongo_db.ai_usage.count_documents({"user_id": pro_session["user_id"], "kind": "jd_scanner"})
    assert cnt >= 1


# ============ Existing endpoints still work for free users ============
def test_existing_optimize_resume_still_works_for_free(free_session):
    r = _client(free_session["token"]).post(
        f"{BASE_URL}/api/ai/optimize-resume",
        json={"resume": SHORT_RESUME, "job_description": SHORT_JD},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    assert "result" in r.json()


# ============ Reviews Pro-gating (re-verify) ============
def test_reviews_post_blocks_free(free_session):
    r = _client(free_session["token"]).post(
        f"{BASE_URL}/api/reviews",
        json={"quote": "DashCareer is the best tool ever for tracking applications.", "role": "PM", "rating": 5},
    )
    assert r.status_code == 403
    assert "Pro" in r.json().get("detail", "")


def test_reviews_post_works_for_pro(pro_session, mongo_db):
    r = _client(pro_session["token"]).post(
        f"{BASE_URL}/api/reviews",
        json={"quote": "DashCareer is the best tool ever for tracking applications.", "role": "PM", "rating": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["quote"].startswith("DashCareer")
    assert data["role"] == "PM"
    # verify persisted
    mine = _client(pro_session["token"]).get(f"{BASE_URL}/api/reviews/mine").json()
    assert mine is not None and mine["quote"].startswith("DashCareer")


# ============ DELETE /api/account re-verify (uses isolated user) ============
def test_delete_account_wipes_user(mongo_db):
    uid, tok = _seed_user(mongo_db, "free")
    # Seed an application and ai_usage doc
    mongo_db.applications.insert_one({
        "id": f"TEST_app_{uid}", "user_id": uid, "company": "Acme", "role": "PM",
        "status": "applied", "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.ai_usage.insert_one({
        "user_id": uid, "kind": "resume_optimize",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    r = _client(tok).delete(f"{BASE_URL}/api/account")
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # Everything wiped
    assert mongo_db.users.count_documents({"user_id": uid}) == 0
    assert mongo_db.user_sessions.count_documents({"user_id": uid}) == 0
    assert mongo_db.applications.count_documents({"user_id": uid}) == 0
    assert mongo_db.ai_usage.count_documents({"user_id": uid}) == 0

    # Token now invalid
    r2 = _client(tok).get(f"{BASE_URL}/api/auth/me")
    assert r2.status_code == 401
