# DashCareer — PRD

## Original Problem Statement
Build a premium AI-powered career application platform called DashCareer. Modern, clean, professional (Linear / Stripe / Notion aesthetic). Dark theme, minimal, rounded cards, thin borders, subtle shadows, light animations. Pages: Landing, Login, Sign up, Dashboard, Applications, Documents, AI Tools, Pricing, Settings. AI: resume optimization, cover letter generation, application suggestions. Free plan (≤10 apps, limited AI, 1 template); Pro £7/month (unlimited). Simple DB (users, applications, documents, subscriptions, ai_usage).

## Architecture
- **Frontend**: React 19 (CRA + craco), Tailwind, shadcn/ui, lucide-react, sonner, react-router-dom
- **Backend**: FastAPI, MongoDB (motor), emergentintegrations (Claude Sonnet 4.5)
- **Auth**: Emergent-managed Google OAuth (httpOnly session_token cookie + Bearer fallback)
- **AI**: Claude Sonnet 4.5 via EMERGENT_LLM_KEY (resume / cover letter / suggestions)
- **Payments**: Gumroad (external link from Pricing page)
- **Theme**: Dark by default, Outfit (display) + Figtree (body) fonts

## User Persona
Job seekers — early-career to senior — who want a single, calm place to track applications and get AI help with resumes and cover letters.

## Core Requirements (static)
- Application tracking board (Applied / Interview / Accepted / Rejected)
- Upcoming deadlines on dashboard + analytics cards (Total, Interviews, Accepted, Response %)
- Documents library (resumes + cover letters)
- AI tools (3 features only, kept minimal for cost)
- Plan-based limits (Free: 10 apps + 5 AI/day; Pro: unlimited)
- Pricing page with Gumroad CTA
- Login via Google only

## What's Implemented (2026-02)
- ✅ Backend: /api/auth/{session,me,logout}, /api/applications (CRUD), /api/documents (CRUD), /api/ai/{optimize-resume,cover-letter,suggestions}, /api/analytics/overview
- ✅ Frontend: Landing, Login, AuthCallback, Dashboard, Applications (Kanban), Documents, AI Tools, Pricing, Settings
- ✅ Emergent Google OAuth (session_id hash → backend session exchange → httpOnly cookie)
- ✅ Claude Sonnet 4.5 integration via emergentintegrations + EMERGENT_LLM_KEY
- ✅ Free-plan limits enforced server-side (10 apps, 5 AI/day)
- ✅ Premium dark UI with Outfit/Figtree fonts, grid hero background, glass navbar
- ✅ End-to-end testing: 100% backend (11/11), 100% frontend critical flows

## Prioritized Backlog
### P1
- Drag-and-drop on the Kanban board (currently uses status dropdown)
- Real Gumroad webhook → upgrade `plan` to `pro` automatically
- Deadline reminders (email or in-app banner)
- Save AI output directly as a Document
### P2
- Premium resume templates (PDF export)
- Import job from URL (paste link → autofill company/role)
- Tags / search / filter on applications
- Settings: export all data as JSON
### P3
- Browser extension to clip listings
- Stats over time (recharts already installed)

## Next Tasks
1. Drag-and-drop status updates with optimistic UI
2. Pro plan activation flow (Gumroad license key entry in Settings)
3. Deadline email reminders (cron + Resend)
