from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import requests as http_requests
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage
from reminders import start_scheduler, stop_scheduler, generate_reminders
from personality import all_questions, score_answers, get_result, TYPES


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
GUMROAD_PRODUCT_PERMALINK = os.environ.get('GUMROAD_PRODUCT_PERMALINK', '')

app = FastAPI()
api_router = APIRouter(prefix="/api")


# ============ MODELS ============
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    plan: str = "free"
    created_at: datetime


class Application(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    company: str
    role: str
    status: Literal["applied", "interview", "offer", "rejected"] = "applied"
    location: Optional[str] = ""
    salary: Optional[str] = ""
    notes: Optional[str] = ""
    deadline: Optional[str] = None
    applied_date: Optional[str] = None
    link: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_changed_at: Optional[str] = None


class ApplicationCreate(BaseModel):
    company: str
    role: str
    status: Optional[str] = "applied"
    location: Optional[str] = ""
    salary: Optional[str] = ""
    notes: Optional[str] = ""
    deadline: Optional[str] = None
    applied_date: Optional[str] = None
    link: Optional[str] = ""


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    notes: Optional[str] = None
    deadline: Optional[str] = None
    applied_date: Optional[str] = None
    link: Optional[str] = None


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    type: Literal["resume", "cover_letter"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentCreate(BaseModel):
    title: str
    type: Literal["resume", "cover_letter"]
    content: str


class ResumeOptimizeRequest(BaseModel):
    resume: str
    job_description: Optional[str] = ""


class CoverLetterRequest(BaseModel):
    resume: str
    company: str
    role: str
    job_description: Optional[str] = ""


class SuggestionsRequest(BaseModel):
    role: str
    skills: Optional[str] = ""


class CVRewriteRequest(BaseModel):
    resume: str
    target_role: str
    job_description: Optional[str] = ""


class InterviewPrepRequest(BaseModel):
    role: str
    job_description: Optional[str] = ""


class JDScannerRequest(BaseModel):
    resume: str
    job_description: str


class PersonalitySubmit(BaseModel):
    answers: List[int]


class Reminder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    app_id: str
    kind: str
    headline: str
    message: str
    company: str = ""
    role: str = ""
    read: bool = False
    created_at: datetime


class LicenseActivateRequest(BaseModel):
    license_key: str


class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    role: str
    quote: str
    rating: int = 5
    approved: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewCreate(BaseModel):
    quote: str
    role: str
    rating: Optional[int] = 5


# ============ AUTH ============
async def get_current_user(request: Request) -> User:
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    if isinstance(user_doc.get("created_at"), str):
        user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
    return User(**user_doc)


@api_router.post("/auth/session")
async def auth_session(request: Request, response: Response):
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    r = http_requests.get(
        "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
        headers={"X-Session-ID": session_id},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()

    email = data["email"]
    name = data["name"]
    picture = data.get("picture", "")
    session_token = data["session_token"]

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "plan": "free",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "picture": picture,
    }


@api_router.get("/auth/me", response_model=User)
async def auth_me(user: User = Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"ok": True}


@api_router.delete("/account")
async def delete_account(response: Response, user: User = Depends(get_current_user)):
    """Permanently delete the user and all their data."""
    uid = user.user_id
    # Wipe everything user-scoped
    await db.applications.delete_many({"user_id": uid})
    await db.documents.delete_many({"user_id": uid})
    await db.ai_usage.delete_many({"user_id": uid})
    await db.reviews.delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.users.delete_one({"user_id": uid})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
    return {"ok": True}


# ============ APPLICATIONS ============
@api_router.get("/applications", response_model=List[Application])
async def list_applications(user: User = Depends(get_current_user)):
    docs = await db.applications.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return docs


@api_router.post("/applications", response_model=Application)
async def create_application(payload: ApplicationCreate, user: User = Depends(get_current_user)):
    # Free plan limit
    if user.plan == "free":
        count = await db.applications.count_documents({"user_id": user.user_id})
        if count >= 10:
            raise HTTPException(status_code=403, detail="Free plan limit reached (10 applications). Upgrade to Pro.")

    app_obj = Application(user_id=user.user_id, status_changed_at=datetime.now(timezone.utc).isoformat(), **payload.model_dump(exclude_none=True))
    doc = app_obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.applications.insert_one(doc)
    return app_obj


@api_router.patch("/applications/{app_id}", response_model=Application)
async def update_application(app_id: str, payload: ApplicationUpdate, user: User = Depends(get_current_user)):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No updates provided")

    # If status is changing, stamp status_changed_at
    if "status" in update:
        existing = await db.applications.find_one({"id": app_id, "user_id": user.user_id}, {"status": 1, "_id": 0})
        if existing and existing.get("status") != update["status"]:
            update["status_changed_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.applications.update_one(
        {"id": app_id, "user_id": user.user_id},
        {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    doc = await db.applications.find_one({"id": app_id, "user_id": user.user_id}, {"_id": 0})
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return doc


@api_router.delete("/applications/{app_id}")
async def delete_application(app_id: str, user: User = Depends(get_current_user)):
    result = await db.applications.delete_one({"id": app_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ============ DOCUMENTS ============
@api_router.get("/documents", response_model=List[Document])
async def list_documents(user: User = Depends(get_current_user)):
    docs = await db.documents.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return docs


@api_router.post("/documents", response_model=Document)
async def create_document(payload: DocumentCreate, user: User = Depends(get_current_user)):
    doc_obj = Document(user_id=user.user_id, **payload.model_dump())
    doc = doc_obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.documents.insert_one(doc)
    return doc_obj


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: User = Depends(get_current_user)):
    result = await db.documents.delete_one({"id": doc_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ============ AI TOOLS ============
async def check_ai_quota(user: User):
    if user.plan == "pro":
        return
    today = datetime.now(timezone.utc).date().isoformat()
    count = await db.ai_usage.count_documents({"user_id": user.user_id, "date": today})
    if count >= 5:
        raise HTTPException(status_code=403, detail="Free plan: daily AI limit (5) reached. Upgrade to Pro.")


async def log_ai_usage(user_id: str, kind: str):
    today = datetime.now(timezone.utc).date().isoformat()
    await db.ai_usage.insert_one({
        "user_id": user_id,
        "kind": kind,
        "date": today,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def call_claude(system_msg: str, user_msg: str) -> str:
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"dashcareer_{uuid.uuid4().hex[:8]}",
        system_message=system_msg,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    response = await chat.send_message(UserMessage(text=user_msg))
    return response


@api_router.post("/ai/optimize-resume")
async def optimize_resume(payload: ResumeOptimizeRequest, user: User = Depends(get_current_user)):
    await check_ai_quota(user)
    sys_msg = "You are a senior career coach and resume optimization expert. Provide concise, actionable improvements with bullet points. Keep responses under 400 words."
    user_msg = f"Optimize this resume:\n\n{payload.resume}\n\nTarget Job Description:\n{payload.job_description or 'General improvement'}\n\nProvide: 1) 5 specific improvement suggestions, 2) 3 missing keywords to add, 3) A rewritten 'Professional Summary' (3 lines)."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "resume_optimize")
    return {"result": result}


@api_router.post("/ai/cover-letter")
async def cover_letter(payload: CoverLetterRequest, user: User = Depends(get_current_user)):
    await check_ai_quota(user)
    sys_msg = "You are a professional cover letter writer. Generate concise, compelling cover letters that are strictly between 250 and 300 words, structured as 3-4 short paragraphs (intro, fit, impact, sign-off)."
    user_msg = f"Write a cover letter for:\nCompany: {payload.company}\nRole: {payload.role}\nJob Description: {payload.job_description or 'Not provided'}\n\nApplicant resume:\n{payload.resume}\n\nMUST be 250-300 words. Professional, specific, no clichés."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "cover_letter")
    return {"result": result}


@api_router.post("/ai/suggestions")
async def ai_suggestions(payload: SuggestionsRequest, user: User = Depends(get_current_user)):
    await check_ai_quota(user)
    sys_msg = "You are a career strategist. Provide application strategy suggestions in a short, clear list."
    user_msg = f"For someone targeting the role of {payload.role} with skills: {payload.skills or 'general'}, provide:\n1) 5 companies worth applying to (industry/type, not specific names if uncertain)\n2) 4 key skills to highlight\n3) 3 application tips\nKeep total under 250 words."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "suggestions")
    return {"result": result}


def require_pro(user: User):
    if user.plan != "pro":
        raise HTTPException(status_code=403, detail="This feature is Pro-only. Upgrade for £7/month to unlock.")


@api_router.post("/ai/cv-rewrite")
async def cv_rewrite(payload: CVRewriteRequest, user: User = Depends(get_current_user)):
    require_pro(user)
    sys_msg = "You are an elite executive CV writer. Produce a complete section-by-section rewrite — clearer, stronger, tailored to the target role. Output structured markdown with these sections: ## Professional Summary, ## Core Skills, ## Experience (rewritten bullets with quantified impact), ## Education, ## Optional Extras. Keep tone confident, specific, no clichés."
    user_msg = f"Target role: {payload.target_role}\nJob description (optional): {payload.job_description or 'Not provided'}\n\nOriginal CV:\n{payload.resume}\n\nRewrite this CV in full, tailored to the target role. Strengthen weak bullets, quantify impact where reasonable, remove fluff."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "cv_rewrite")
    return {"result": result}


@api_router.post("/ai/interview-prep")
async def interview_prep(payload: InterviewPrepRequest, user: User = Depends(get_current_user)):
    require_pro(user)
    sys_msg = "You are a senior hiring manager and interview coach. Produce role-specific interview questions with practical answer guidance. Output structured markdown."
    user_msg = f"Role: {payload.role}\nJob description (optional): {payload.job_description or 'Not provided'}\n\nProduce:\n## 8 Likely Interview Questions\nFor each: the question, then a 2-3 line 'How to answer confidently' guide using STAR structure where applicable.\n\n## 3 Questions to Ask the Interviewer\nSharp, role-specific questions that demonstrate insight.\n\nKeep total under 600 words."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "interview_prep")
    return {"result": result}


@api_router.post("/ai/jd-scanner")
async def jd_scanner(payload: JDScannerRequest, user: User = Depends(get_current_user)):
    require_pro(user)
    if not payload.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required")
    sys_msg = "You are an ATS expert and recruiter. Scan a resume against a job description and surface gaps. Be specific and ruthless. Output structured markdown."
    user_msg = f"Job Description:\n{payload.job_description}\n\nCandidate Resume:\n{payload.resume}\n\nProduce:\n## Match Score\nA single % score (0-100) with one-line justification.\n\n## Required Skills Present\nBullet list of skills the candidate already has that match the JD.\n\n## Missing Keywords\nBullet list of exact keywords from the JD missing in the resume.\n\n## Skill Gaps\n3 areas to strengthen before applying.\n\n## Quick Wins\n3 specific edits the candidate can make in the next 10 minutes to improve match.\n\nKeep total under 500 words."
    result = await call_claude(sys_msg, user_msg)
    await log_ai_usage(user.user_id, "jd_scanner")
    return {"result": result}


# ============ BILLING (Gumroad) ============
@api_router.post("/billing/activate-license")
async def activate_license(payload: LicenseActivateRequest, user: User = Depends(get_current_user)):
    if not GUMROAD_PRODUCT_PERMALINK:
        raise HTTPException(status_code=500, detail="Gumroad product not configured")

    license_key = payload.license_key.strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="License key required")

    try:
        r = http_requests.post(
            "https://api.gumroad.com/v2/licenses/verify",
            data={
                "product_permalink": GUMROAD_PRODUCT_PERMALINK,
                "license_key": license_key,
                "increment_uses_count": "true",
            },
            timeout=10,
        )
        data = r.json()
    except Exception:
        logger.exception("Gumroad verify failed")
        raise HTTPException(status_code=502, detail="Could not reach Gumroad")

    if not data.get("success"):
        raise HTTPException(status_code=400, detail=data.get("message") or "Invalid license key")

    purchase = data.get("purchase", {}) or {}
    if purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("disputed"):
        raise HTTPException(status_code=400, detail="License is no longer valid (refunded or disputed)")

    # Optional: enforce one license per user (Gumroad already prevents reuse via increment_uses_count > 1)
    # Mark plan as pro and store license key
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "plan": "pro",
            "gumroad_license_key": license_key,
            "gumroad_purchase_email": purchase.get("email", ""),
            "pro_activated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "ok": True,
        "plan": "pro",
        "purchase_email": purchase.get("email", ""),
    }


@api_router.post("/billing/deactivate")
async def deactivate(user: User = Depends(get_current_user)):
    """Downgrade self to free (for testing / customer-initiated downgrade)."""
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"plan": "free"}, "$unset": {"gumroad_license_key": "", "gumroad_purchase_email": "", "pro_activated_at": ""}},
    )
    return {"ok": True, "plan": "free"}


# ============ REVIEWS ============
@api_router.get("/reviews")
async def list_public_reviews():
    docs = await db.reviews.find({"approved": True}, {"_id": 0, "user_id": 0}).sort("created_at", -1).limit(6).to_list(6)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return docs


@api_router.get("/reviews/mine")
async def my_review(user: User = Depends(get_current_user)):
    doc = await db.reviews.find_one({"user_id": user.user_id}, {"_id": 0})
    if not doc:
        return None
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return doc


@api_router.post("/reviews", response_model=Review)
async def submit_review(payload: ReviewCreate, user: User = Depends(get_current_user)):
    if user.plan != "pro":
        raise HTTPException(status_code=403, detail="Only Pro users can submit reviews. Upgrade to share your experience.")
    quote = payload.quote.strip()
    role = payload.role.strip()
    if len(quote) < 20:
        raise HTTPException(status_code=400, detail="Quote must be at least 20 characters")
    if len(quote) > 300:
        raise HTTPException(status_code=400, detail="Quote must be 300 characters or fewer")
    if not role:
        raise HTTPException(status_code=400, detail="Role is required")
    rating = max(1, min(5, payload.rating or 5))

    review_obj = Review(
        user_id=user.user_id,
        name=user.name,
        role=role,
        quote=quote,
        rating=rating,
    )
    doc = review_obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    # Upsert one review per user
    await db.reviews.update_one(
        {"user_id": user.user_id},
        {"$set": doc},
        upsert=True,
    )
    return review_obj


@api_router.delete("/reviews/mine")
async def delete_my_review(user: User = Depends(get_current_user)):
    await db.reviews.delete_one({"user_id": user.user_id})
    return {"ok": True}


# ============ ANALYTICS ============
@api_router.get("/analytics/overview")
async def analytics_overview(user: User = Depends(get_current_user)):
    total = await db.applications.count_documents({"user_id": user.user_id})
    by_status = {}
    for s in ["applied", "interview", "offer", "rejected"]:
        by_status[s] = await db.applications.count_documents({"user_id": user.user_id, "status": s})

    response_rate = 0
    if total > 0:
        responses = by_status["interview"] + by_status["offer"]
        response_rate = round((responses / total) * 100)

    today = datetime.now(timezone.utc).date().isoformat()
    ai_today = await db.ai_usage.count_documents({"user_id": user.user_id, "date": today})

    return {
        "total": total,
        "by_status": by_status,
        "response_rate": response_rate,
        "ai_used_today": ai_today,
        "plan": user.plan,
    }


@api_router.get("/analytics/streak")
async def analytics_streak(user: User = Depends(get_current_user)):
    """Count interview+offer wins in the last 7 days based on status_changed_at."""
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    wins = await db.applications.count_documents({
        "user_id": user.user_id,
        "status": {"$in": ["interview", "offer"]},
        "status_changed_at": {"$gte": seven_days_ago},
    })
    return {"wins_7d": wins}


@api_router.get("/")
async def root():
    return {"message": "DashCareer API"}


# ============ PERSONALITY ============
@api_router.get("/personality/questions")
async def personality_questions():
    return {"questions": all_questions(), "total": len(all_questions())}


@api_router.get("/personality/types")
async def personality_types():
    return TYPES


@api_router.get("/personality/me")
async def personality_me(user: User = Depends(get_current_user)):
    doc = await db.personality_results.find_one({"user_id": user.user_id}, {"_id": 0})
    if not doc:
        return None
    return doc


@api_router.post("/personality/submit")
async def personality_submit(payload: PersonalitySubmit, user: User = Depends(get_current_user)):
    if len(payload.answers) != 20:
        raise HTTPException(status_code=400, detail="20 answers required")
    if any(a < 0 or a > 3 for a in payload.answers):
        raise HTTPException(status_code=400, detail="Each answer must be 0–3")
    try:
        mbti = score_answers(payload.answers)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = get_result(mbti)
    doc = {
        "user_id": user.user_id,
        "type": mbti,
        "result": result,
        "answers": payload.answers,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.personality_results.update_one(
        {"user_id": user.user_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


@api_router.delete("/personality/me")
async def personality_delete(user: User = Depends(get_current_user)):
    await db.personality_results.delete_one({"user_id": user.user_id})
    return {"ok": True}


# ============ REMINDERS ============
@api_router.get("/reminders")
async def list_reminders(user: User = Depends(get_current_user)):
    docs = await db.reminders.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return docs


@api_router.post("/reminders/{reminder_id}/read")
async def mark_reminder_read(reminder_id: str, user: User = Depends(get_current_user)):
    """reminder_id is the composite app_id+kind path. We accept app_id and kind via path-like format app_id::kind."""
    if "::" not in reminder_id:
        raise HTTPException(status_code=400, detail="Bad reminder id")
    app_id, kind = reminder_id.split("::", 1)
    await db.reminders.update_one(
        {"user_id": user.user_id, "app_id": app_id, "kind": kind},
        {"$set": {"read": True}},
    )
    return {"ok": True}


@api_router.post("/reminders/dismiss-all")
async def dismiss_all_reminders(user: User = Depends(get_current_user)):
    await db.reminders.update_many({"user_id": user.user_id}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/reminders/run-now")
async def reminders_run_now(user: User = Depends(get_current_user)):
    """Manual trigger — Pro only. Useful for testing and 'check now' button."""
    require_pro(user)
    count = await generate_reminders(db)
    return {"ok": True, "emitted": count}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_db_client():
    start_scheduler(db)


@app.on_event("shutdown")
async def shutdown_db_client():
    stop_scheduler()
    client.close()
