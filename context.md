# Client Onboarding Platform — Full Development Context

## What Was Built

A multi-tenant SaaS platform for marketing agencies to onboard clients with AI-powered tools and strategy documents. Built with Python/Flask, SQLite, OpenAI GPT-4, and vanilla JS.

**Live URL:** `https://seahorse-app-j9ivs.ondigitalocean.app`
**GitHub:** `https://github.com/k230748-wq/OnBoarding.git`
**Hosting:** DigitalOcean App Platform ($24/mo, 2 instances)

---

## Architecture

```
app.py              # Main Flask app — all routes, auth, background processing (~1990 lines)
database.py         # SQLite layer — 16 tables, all CRUD functions (~1010 lines)
services/           # External integrations (AI, email, ClickUp, Airtable)
utils/              # Logger, validators, PDF generator
templates/          # 21 Jinja2 HTML templates (public, client dashboard, admin)
static/             # CSS (glassmorphic), JS (modern-app, confetti, particle-text)
```

### Multi-Tenancy Model
- Each agency gets a URL slug: `/a/<slug>/...`
- Agency branding (colors, logo, name) stored in `agencies` table
- Templates dynamically apply agency branding via Jinja2 context
- Separate auth: agency owners (`session['owner_id']`) vs clients (`session['client_onboarding_id']`)

### Background Processing
- `process_onboarding()` runs in `threading.Thread`
- Creates ClickUp tasks, Airtable records, generates AI documents from dynamic templates, sends emails
- Updates onboarding status in DB on completion/failure

---

## Features Implemented

### 1. Dynamic Onboarding Form Builder
- Agency owners configure form sections and questions via admin UI (`/admin/onboarding-setup`)
- 8 default sections seeded per agency (Basic Info, Service Selection, Business Overview, etc.)
- Questions support types: text, email, phone, url, textarea, select, date
- Required/optional per question, drag-to-reorder
- Client-facing form at `/a/<slug>` renders dynamically from DB config

### 2. Dynamic Document Generation
- 10 default document templates seeded per agency
- Each template links to specific form sections for context
- AI generates documents using linked section answers as context
- Documents viewable as HTML, downloadable as PDF
- Regeneration supported from client dashboard

### 3. Client Dashboard (6 AI Tools)
- **Content Calendar** — Plan/schedule content with drag-and-drop calendar UI
- **Competitor Analysis** — AI-powered competitor breakdown with CRUD
- **Campaign Ideas** — Tailored campaign concepts with stages (idea → planning → active)
- **Audience Personas** — Detailed buyer personas with demographics/psychographics
- **Social Copy Generator** — Platform-specific captions with favorites
- **SEO Keywords** — Keyword research with clusters, difficulty, intent tracking

Each tool has: AI generation, manual CRUD, list/detail views, PDF export.

### 4. AI Chat
- GPT-4 powered chat on client dashboard
- Context-aware: knows client's industry, services, goals, challenges
- Conversation history maintained per session

### 5. Meeting Requests
- Clients request meetings from dashboard
- Email notification sent to agency owner
- Admin meetings page with pending/confirmed/completed status
- Airtable sync for next meeting info

### 6. Per-Agency Airtable Integration
- Agency owners configure their own Airtable Personal Access Token + Base ID in admin settings
- "Create Clients Table" button auto-creates a 20-field Clients table via pyairtable API
- Fields: Company Name, Email, Phone, Website, Primary Contact, Service Type, Status, Onboarding ID, Onboarded At, Start Date, Budget, Duration, Business Description, Target Market, Challenges, Goals, Documents Generated, Next Meeting, Meeting Topic, Notes
- Auto-syncs on: onboarding submit, onboarding complete (status + doc count), meeting request
- Each agency's Airtable is independent — only visible to that agency owner

### 7. Global Gmail/SMTP Notifications
- Single email config from `.env` (not per-agency)
- Sends: client welcome email (with auto-generated password), owner notification, meeting alerts, admin mail
- Currently configured: `igwork112@gmail.com` via Gmail App Password
- `NotificationService` reads from env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFICATION_EMAIL`

### 8. Admin Dashboard
- **Clients list** — all onboardings with status, click for detail
- **Client detail** — full onboarding data, documents, meeting history
- **Settings** — agency name, slug, logo URL, brand colors (live preview), Airtable config
- **Meetings** — pending/confirmed/completed meeting requests
- **Mail** — send emails to any onboarded client
- **Onboarding Setup** — form sections, questions, document templates CRUD

### 9. Auth System
- Owner registration with reusable invite code (`STARTER2026`)
- Owner login with SHA256 password hashing
- Client accounts auto-created during onboarding with generated password
- `@login_required` decorator on all 22 admin routes
- `client_login_required(slug, onboarding_id)` on all 40 client routes
- Owners can view their clients' dashboards
- Separate logout flows for owners and clients

---

## Database (16 Tables)

| Table | Purpose |
|-------|---------|
| `agencies` | Tenant data (name, slug, colors, logo, airtable config) |
| `agency_owners` | Owner accounts (email, password_hash, agency_id) |
| `invite_codes` | Registration codes (reusable, default: STARTER2026) |
| `client_accounts` | Client login credentials (tied to onboarding_id) |
| `onboardings` | Master records — JSON blob with all onboarding data |
| `form_sections` | Dynamic onboarding form sections per agency |
| `form_questions` | Dynamic questions within form sections |
| `document_templates` | AI document templates with linked sections |
| `meeting_requests` | Client meeting requests with status |
| `calendar_posts` | Content calendar entries |
| `competitors` | Competitor analysis data |
| `campaigns` | Campaign ideas |
| `personas` | Audience persona data |
| `copy_library` | Social media copy with favorites |
| `seo_keywords` | SEO keyword research data |
| `tool_outputs` | AI-generated tool results |

---

## Environment Variables

```bash
# Required
SECRET_KEY=onboarding-platform-secret-2026
OPENAI_API_KEY=sk-proj-...

# Email (Gmail)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=igwork112@gmail.com
SMTP_PASSWORD=pdckfvxshcbfksij
NOTIFICATION_EMAIL=igwork112@gmail.com

# Optional (services degrade gracefully)
CLICKUP_API_TOKEN=
CLICKUP_TEAM_ID=
CLICKUP_SPACE_ID=
```

Airtable credentials are per-agency (stored in `agencies` table, configured in admin settings).

---

## Deployment

- **Platform:** DigitalOcean App Platform
- **GitHub auto-deploy:** Pushes to `main` trigger automatic redeploy
- **Procfile:** `web: gunicorn app:app --bind 0.0.0.0:8080 --workers 2 --timeout 120`
- **Runtime:** Python 3.11.6
- **Port:** Reads from `PORT` env var, defaults to 8080

### Deployment Files
- `Procfile` — Gunicorn config
- `runtime.txt` — Python version
- `requirements.txt` — flask, python-dotenv, requests, openai, pyairtable, fpdf2, gunicorn
- `.gitignore` — excludes .env, *.db, __pycache__, logs/, .DS_Store

---

## Route Map

### Public (no auth)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Landing page |
| GET/POST | `/register` | Owner registration (invite code required) |
| GET/POST | `/login` | Owner login |
| GET | `/logout` | Owner logout |
| GET | `/health` | Basic health check |
| GET | `/health/detailed` | Detailed service status |

### Per-Agency Public
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/a/<slug>` | Agency landing + onboarding form |
| POST | `/a/<slug>/onboard` | Submit onboarding (JSON) |
| GET/POST | `/a/<slug>/login` | Client login |
| GET | `/a/<slug>/logout-client` | Client logout |

### Admin (owner auth required)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin` | Dashboard — client list |
| GET/POST | `/admin/settings` | Agency settings |
| GET | `/admin/meetings` | Meeting management |
| POST | `/admin/meetings/<id>/status` | Update meeting status |
| GET/POST | `/admin/mail` | Send emails to clients |
| GET | `/admin/onboarding-setup` | Form builder UI |
| GET | `/admin/client/<oid>` | Client detail view |
| POST | `/admin/api/airtable/setup` | Create Airtable Clients table |
| POST/PUT/DELETE | `/admin/api/sections/...` | Form section CRUD |
| POST/PUT/DELETE | `/admin/api/questions/...` | Form question CRUD |
| POST/PUT/DELETE | `/admin/api/templates/...` | Document template CRUD |
| POST | `/admin/api/sections/reorder` | Reorder sections |
| POST | `/admin/api/questions/reorder` | Reorder questions |

### Client Dashboard (client or owner auth)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/a/<slug>/dashboard/<oid>` | Overview tab |
| GET | `/a/<slug>/dashboard/<oid>/documents` | Documents tab |
| GET | `/a/<slug>/dashboard/<oid>/tools` | Tools tab |
| GET | `/a/<slug>/dashboard/<oid>/tool/<type>` | Individual tool page |
| POST | `/a/<slug>/dashboard/<oid>/tool/<type>/generate` | AI generate for tool |
| POST | `/a/<slug>/dashboard/<oid>/tool/<type>/<id>/delete` | Delete tool output |
| GET | `/a/<slug>/dashboard/<oid>/tool/<type>/<id>/pdf` | PDF download |
| POST | `/a/<slug>/dashboard/<oid>/request-meeting` | Request meeting (JSON) |
| POST | `/a/<slug>/dashboard/<oid>/regenerate-documents` | Regenerate all docs |
| POST | `/a/<slug>/dashboard/<oid>/chat` | AI chat (JSON) |

### CRUD APIs (client or owner auth, JSON)
| Resource | GET list | POST create | PUT update | DELETE |
|----------|----------|-------------|------------|--------|
| Competitors | `/competitors` | `/competitors` | `/competitors/<id>` | `/competitors/<id>` |
| Campaigns | `/campaigns` | `/campaigns` | `/campaigns/<id>` | `/campaigns/<id>` |
| Personas | `/personas` | `/personas` | `/personas/<id>` | `/personas/<id>` |
| Social Copy | `/copies` | `/copies` | — | `/copies/<id>` |
| SEO Keywords | `/keywords` | `/keywords` | `/keywords/<id>` | `/keywords/<id>` |
| Calendar | `/calendar/posts` | `/calendar/posts` | `/calendar/posts/<id>` | `/calendar/posts/<id>` |

All CRUD paths prefixed with `/a/<slug>/dashboard/<oid>/`.

AI generation endpoints: `/competitors/ai-generate`, `/campaigns/ai-generate`, `/personas/ai-generate`, `/copies/ai-generate`, `/keywords/ai-generate`, `/calendar/ai-generate`.

---

## QA Test Results (27/27 Passed)

1. Public pages (landing, login, register, health)
2. Owner registration with invite code STARTER2026
3. Owner login + session management
4. All 5 admin pages
5. Admin settings update (name, colors, logo)
6. Onboarding setup seeding (8 sections, 10 templates)
7. Agency public pages + dynamic form config
8. Client onboarding submission + background processing
9. Client account auto-creation
10. Client dashboard (overview, documents, tools)
11. All 6 tool pages
12. All CRUD API GETs
13. Full CRUD (create/update/delete) for all 6 tools
14. Meeting requests + email notification
15. Admin client detail
16. Admin mail
17. AI chat (GPT-4)
18. AI tool generation + PDF download
19. Document regeneration
20. Auth security (admin, dashboard, API blocked without session)
21. Invite code reusability
22. Health checks (basic + detailed)
23. Logout (owner + client)
24. Onboarding setup CRUD (sections, questions, templates, reorder)
25. Admin email send
26. Airtable setup (proper error without credentials)
27. Database integrity (16 tables)

---

## Development History

### Session 1 — Dynamic Onboarding Form Builder
- Designed and implemented dynamic form sections + questions system
- Built admin onboarding setup UI with drag-and-drop reorder
- Created document template system with section linking
- AI document generation using linked section context
- 12 implementation tasks completed

### Session 2 — Full App Audit & Fixes
- E2E verification of dynamic onboarding feature
- Fixed auth on 38 unprotected routes
- Removed dead code (5 unused methods in ai_generator, 5 in notifications)
- Fixed hardcoded agency name "Ignite Media" across codebase
- Fixed email links to use full URLs
- Updated requirements.txt (added fpdf2, removed python-dateutil)

### Session 3 — Airtable + Email + Deployment
- Implemented per-agency Airtable integration (token in admin settings, auto-create table, sync records)
- Added Gmail/SMTP as global notification service
- Reverted per-agency SMTP back to global (user decision)
- Configured Gmail: igwork112@gmail.com with App Password
- Made invite codes reusable + seeded STARTER2026
- Created deployment files (Procfile, runtime.txt, .gitignore)
- Pushed to GitHub and deployed to DigitalOcean App Platform
- QA fixes: SMTP_PASS typo, configurable PORT
- Full 27-group QA test — all passed

---

## Known Limitations

- No automated test suite — manual/script testing only
- `app.py` is a single large file (~1990 lines) — not yet split into blueprints
- SHA256 password hashing (not bcrypt/argon2)
- SQLite — single-writer, no concurrent write support
- No CSRF protection on forms
- No rate limiting on API endpoints
- ClickUp integration disabled (no credentials configured)
- `get_client_account_by_onboarding()` in database.py is unused

## Valid Service Types

Used throughout the system (forms, ClickUp tasks, AI prompts, Airtable):
- `social_media`
- `content_marketing`
- `paid_ads`
- `seo`
- `branding`
