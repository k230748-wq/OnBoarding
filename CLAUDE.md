# Client Onboarding Platform — Project CLAUDE.md

## Project Overview

**What:** Multi-tenant SaaS platform for marketing agencies to onboard clients with AI-powered tools and strategy documents.

**Stack:** Python 3, Flask 3.0.0, SQLite3, OpenAI GPT-4, Jinja2 templates, vanilla JS/CSS

**Integrations:** ClickUp (task management), Airtable (records), SMTP email, OpenAI API

**Current Agency:** "The Sol" (thesole.ai) — configurable per tenant via admin settings

## Architecture

```
app.py              # Main Flask app — routes, auth, background processing (~1930 lines)
database.py         # SQLite layer — 16 tables, all CRUD functions (~990 lines)
services/           # External service integrations (AI, email, ClickUp, Airtable)
utils/              # Logger, validators, PDF generator
templates/          # Jinja2 HTML (21 templates: public, client dashboard, admin, auth)
static/             # CSS (glassmorphic), JS (modern-app, confetti, particle-text)
```

### Multi-Tenancy Model

- Each agency gets a URL slug: `/a/<slug>/...`
- Agency branding (colors, logo, name) stored in `agencies` table
- Templates dynamically apply agency branding via Jinja2 context
- Separate auth flows: agency owners (session `owner_id`) vs clients (session `client_onboarding_id`)

### Background Processing

- `process_onboarding()` runs in `threading.Thread` for async work
- Creates ClickUp tasks, Airtable records, generates AI documents from dynamic templates, sends emails
- Updates onboarding status in DB on completion/failure

## Critical Rules

### Database

- All queries use `database.py` functions — never write raw SQL in `app.py`
- `get_db()` is a context manager with auto-commit/rollback — always use `with get_db() as conn:`
- UUIDs (v4) for all primary keys — `str(uuid.uuid4())`
- ISO datetime strings for all timestamps — `datetime.now().isoformat()`
- `PRAGMA foreign_keys = ON` is set in every connection
- Prepared statements (parameterized queries) for all user input — no string formatting in SQL

### Authentication

- Passwords hashed with SHA256 via `hash_password()` in app.py
- Owner auth: `session['owner_id']` checked by `@login_required` decorator
- Client auth: `session['client_onboarding_id']` checked by `client_login_required(slug, onboarding_id)` — also allows owners to view their clients' dashboards
- Client passwords are auto-generated during onboarding, emailed to client
- Two completely separate session flows — owners and clients never share auth state

### Services

- All 4 services initialize with graceful fallback — if credentials missing, service is `None`
- Always check `if ai_generator:` / `if notification_service:` before calling
- Services read credentials from environment variables via `os.getenv()`
- Retry logic (3 attempts, exponential backoff) in notifications, clickup, airtable

### AI Generation

- Uses OpenAI GPT-4 (`gpt-4` model) via the `openai` Python SDK
- System prompts define agency persona and output format
- All AI content returned as markdown — rendered to HTML for display, PDF for download
- 6 client tools: content_calendar, competitors, campaigns, personas, social_copy, seo_keywords
- Tool outputs saved to `tool_outputs` table for persistence

### Code Style

- No type hints currently used — do not add them unless asked
- f-strings for all string formatting
- Logging via `utils.logger.setup_logger()` singleton — use `logger.info/warning/error`
- No docstrings on route handlers — do not add them unless asked
- Single quotes for strings throughout
- Imports: stdlib first, then third-party, then local (already followed)

### Templates

- All templates use Jinja2 with agency context variables: `agency`, `onboarding`, `active_tab`
- Dynamic theming via `agency.primary_color` and `agency.secondary_color` in inline CSS
- Client dashboard uses tab-based navigation: overview, documents, tools (meetings via modal on overview)
- Tool pages follow consistent pattern: form input -> AI generate -> saved outputs list

### Routes

- Public pages: `/`, `/register`, `/login`
- Admin: `/admin`, `/admin/settings`, `/admin/onboarding-setup`, `/admin/meetings`, `/admin/mail`, `/admin/client/<id>`
- Per-agency public: `/a/<slug>`, `/a/<slug>/onboard`, `/a/<slug>/login`
- Client dashboard: `/a/<slug>/dashboard/<onboarding_id>/...`
- API endpoints return `jsonify()` responses with status codes

## File Structure

```
app.py                          # All routes and business logic
database.py                     # All database operations

services/
  __init__.py
  ai_generator.py               # OpenAI GPT-4 wrapper (AIGenerator class)
  notifications.py              # SMTP email (NotificationService class)
  clickup.py                    # ClickUp API (ClickUpService class)
  airtable_service.py           # Airtable API (AirtableService class)

utils/
  __init__.py
  logger.py                     # Rotating file logger (logs/onboarding_YYYYMMDD.log)
  validators.py                 # Email, date, onboarding form validation
  pdf_generator.py              # Markdown-to-PDF conversion (fpdf)

templates/
  home.html                     # Landing page
  index.html                    # Dynamic multi-step onboarding form (rendered from DB config)
  client_login.html             # Client login
  dashboard.html                # Client dashboard (tabbed)
  document.html                 # Document viewer
  content_calendar.html         # Calendar tool
  tool_page.html                # Generic tool template
  tool_seo.html                 # SEO tool
  tool_campaigns.html           # Campaign tool
  tool_competitors.html         # Competitor analysis tool
  tool_personas.html            # Persona tool
  tool_social_copy.html         # Social copy tool
  error.html                    # Error page
  auth/login.html               # Owner login
  auth/register.html            # Owner registration (invite code required)
  admin/dashboard.html          # Owner dashboard
  admin/settings.html           # Agency branding
  admin/meetings.html           # Meeting management
  admin/mail.html               # Email interface
  admin/client_detail.html      # Client detail view
  admin/onboarding_setup.html   # Dynamic form & document template config

static/
  css/modern-ui.css             # Main stylesheet (glassmorphic, dark theme)
  js/modern-app.js              # App logic (forms, AJAX, tool handlers)
  js/confetti.js                # Celebration animations
  js/particle-text.js           # Text particle effects
```

## Database Tables (16)

| Table | Purpose |
|-------|---------|
| `agencies` | Tenant data (name, slug, branding colors, logo) |
| `agency_owners` | Owner accounts (email, password_hash, agency_id) |
| `invite_codes` | Registration access control |
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

## Environment Variables

```bash
# Required
SECRET_KEY=              # Flask session encryption
OPENAI_API_KEY=          # GPT-4 API access

# Email (required for notifications)
SMTP_HOST=               # e.g., smtp.gmail.com or siteground
SMTP_PORT=587
SMTP_USER=               # Sender email address
SMTP_PASSWORD=           # SMTP password
NOTIFICATION_EMAIL=      # Admin notification recipient

# Optional — services degrade gracefully without these
CLICKUP_API_TOKEN=
CLICKUP_TEAM_ID=
CLICKUP_SPACE_ID=
AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=
AIRTABLE_TABLE_NAME=

# Branding
AGENCY_NAME=             # Default agency name
```

## Running the App

```bash
pip install -r requirements.txt
python app.py
# Runs on http://localhost:8080
```

## Valid Service Types

These are the 5 service types used throughout the system (forms, ClickUp tasks, AI prompts):
- `social_media`
- `content_marketing`
- `paid_ads`
- `seo`
- `branding`

## Known Limitations

- No automated tests — manual testing only
- `app.py` is a single large file (~1930 lines) — not yet split into blueprints
- SHA256 password hashing (not bcrypt/argon2)
- SQLite — single-writer, no concurrent write support
- No CSRF protection on forms
- No rate limiting on API endpoints
- ClickUp and Airtable currently disabled (credentials not configured)
