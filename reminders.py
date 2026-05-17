"""
Smart Reminders service.

Generates reminders for Pro users based on their applications:
  - Deadline reminders (24h before application.deadline)
  - Interview reminders (day-before applied_date if status=interview)
  - Follow-up nudges (7 days after applied_date if still status=applied)

Reminders are persisted to the `reminders` collection (acts as the in-app banner feed)
and optionally emailed via Resend if RESEND_API_KEY is set.

A single scheduled job runs every hour and emits the day's due reminders.
Each (user, application, kind) combination is sent at most once.
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta, date
from typing import Optional

import resend
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
APP_URL = os.environ.get("APP_URL", "")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _render_email(name: str, subject_line: str, body_line: str, cta_url: str) -> str:
    """Plain, deliverable HTML — inline CSS, tables, no external assets."""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;font-family:Arial,sans-serif;padding:40px 20px;">
      <tr><td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:540px;background:#18181b;border:1px solid #27272a;border-radius:12px;padding:32px;">
          <tr><td style="color:#fff;font-size:13px;letter-spacing:2px;text-transform:uppercase;opacity:0.5;padding-bottom:12px;">DashCareer reminder</td></tr>
          <tr><td style="color:#fff;font-size:22px;font-weight:600;padding-bottom:8px;line-height:1.3;">{subject_line}</td></tr>
          <tr><td style="color:#a1a1aa;font-size:15px;line-height:1.6;padding-bottom:24px;">Hey {name},<br/>{body_line}</td></tr>
          <tr><td>
            <a href="{cta_url}" style="display:inline-block;background:#ffffff;color:#000000;text-decoration:none;padding:11px 20px;border-radius:8px;font-weight:600;font-size:14px;">Open DashCareer</a>
          </td></tr>
          <tr><td style="color:#52525b;font-size:11px;padding-top:32px;border-top:1px solid #27272a;margin-top:24px;">You're receiving this because you enabled DashCareer Pro reminders. Disable anytime in Settings.</td></tr>
        </table>
      </td></tr>
    </table>
    """


async def _send_email(to: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set — skipping email to %s", to)
        return False
    try:
        params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Email sent to %s id=%s", to, result.get("id") if isinstance(result, dict) else result)
        return True
    except Exception as e:
        logger.error("Resend send failed: %s", e)
        return False


async def _emit_reminder(db, user: dict, app_doc: dict, kind: str, headline: str, message: str) -> bool:
    """Create a reminder row if not already emitted, and optionally send email. Returns True if newly emitted."""
    key = {"user_id": user["user_id"], "app_id": app_doc["id"], "kind": kind}
    existing = await db.reminders.find_one(key, {"_id": 0})
    if existing:
        return False  # already emitted

    reminder = {
        **key,
        "headline": headline,
        "message": message,
        "company": app_doc.get("company", ""),
        "role": app_doc.get("role", ""),
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reminders.insert_one(reminder)

    # Best-effort email
    if user.get("email"):
        cta = f"{APP_URL}/dashboard/applications" if APP_URL else "https://dashcareer.app"
        html = _render_email(
            name=user.get("name", "there").split(" ")[0],
            subject_line=headline,
            body_line=message,
            cta_url=cta,
        )
        await _send_email(user["email"], headline, html)
    return True


async def generate_reminders(db) -> int:
    """Scan all Pro users' applications and emit due reminders. Returns count emitted."""
    today = _today()
    tomorrow = today + timedelta(days=1)
    week_ago = today - timedelta(days=7)
    emitted = 0

    pro_users = await db.users.find({"plan": "pro"}, {"_id": 0}).to_list(10000)
    for user in pro_users:
        if not user.get("email"):
            continue
        apps = await db.applications.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
        for app in apps:
            deadline = _parse_iso_date(app.get("deadline"))
            applied_date = _parse_iso_date(app.get("applied_date"))
            status = app.get("status", "applied")
            company = app.get("company", "")
            role = app.get("role", "")

            # 1) Deadline reminder — fires when deadline is tomorrow
            if deadline == tomorrow and status not in ("offer", "rejected"):
                if await _emit_reminder(
                    db, user, app, "deadline",
                    f"Deadline tomorrow: {role} at {company}",
                    f"Your application deadline for the {role} role at {company} is tomorrow. Last chance to submit.",
                ):
                    emitted += 1

            # 2) Interview reminder — fires when applied_date == tomorrow AND status is interview
            #    (applied_date is reused as the interview date when status=interview)
            if status == "interview" and applied_date == tomorrow:
                if await _emit_reminder(
                    db, user, app, "interview",
                    f"Interview tomorrow: {role} at {company}",
                    f"You have an interview tomorrow for the {role} role at {company}. Time to prep — open the Interview Prep tool if you haven't.",
                ):
                    emitted += 1

            # 3) Follow-up nudge — applied 7+ days ago, still status=applied
            if status == "applied" and applied_date and applied_date <= week_ago:
                if await _emit_reminder(
                    db, user, app, "followup",
                    f"Follow up with {company}",
                    f"It's been a week since you applied for the {role} role at {company}. A short, polite follow-up email often unlocks a response.",
                ):
                    emitted += 1

    logger.info("Smart Reminders: emitted %d new reminders", emitted)
    return emitted


_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler(db):
    """Start the hourly reminder scan. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")

    async def job():
        try:
            await generate_reminders(db)
        except Exception:
            logger.exception("Reminder scan failed")

    _scheduler.add_job(job, "interval", hours=1, id="reminders_scan", next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30))
    _scheduler.start()
    logger.info("Reminder scheduler started")


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
