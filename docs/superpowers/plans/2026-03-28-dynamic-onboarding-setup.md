# Dynamic Onboarding Setup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let agency owners configure onboarding form questions and AI document templates from the admin panel, replacing the current hardcoded form and 5 fixed documents with a fully dynamic, per-agency system.

**Architecture:** Three new database tables (`form_sections`, `form_questions`, `document_templates`) store per-agency configuration. A seed function populates defaults on agency creation. The client form renders dynamically from the database. Document generation builds AI prompts from template descriptions + linked client answers. The admin gets a new "Onboarding Setup" page with two tabs (Questions / Documents).

**Tech Stack:** Python/Flask, SQLite3, OpenAI GPT-4, Jinja2, vanilla JS

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `database.py` | Modify | Add 3 new tables to `init_db()`, add CRUD functions for sections/questions/templates, add `seed_agency_defaults()`, add `backfill_existing_agencies()` |
| `services/ai_generator.py` | Modify | Add `generate_from_template()` method that builds dynamic prompts |
| `app.py` | Modify | Add admin routes for onboarding setup page, modify `agency_onboard_form()` to pass dynamic sections/questions, modify `agency_onboard()` + `agency_demo()` to accept dynamic fields, modify `process_onboarding()` + `regenerate_documents()` to use dynamic templates |
| `utils/validators.py` | Modify | Replace `validate_onboarding_data()` with dynamic validation |
| `templates/admin/onboarding_setup.html` | Create | Admin page with Questions and Documents tabs |
| `templates/index.html` | Rewrite | Dynamic form rendering from sections/questions |
| `static/js/modern-app.js` | Rewrite | Dynamic form step navigation, validation, and collection |

---

### Task 1: Add new database tables and CRUD functions

**Files:**
- Modify: `database.py:30-211` (init_db) and append new functions after line 664

- [ ] **Step 1: Add the 3 new tables to `init_db()`**

Add after the `onboardings` table (before the closing `'''`):

```python
            CREATE TABLE IF NOT EXISTS form_sections (
                id TEXT PRIMARY KEY,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS form_questions (
                id TEXT PRIMARY KEY,
                section_id TEXT NOT NULL REFERENCES form_sections(id),
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                label TEXT NOT NULL,
                field_key TEXT NOT NULL,
                field_type TEXT NOT NULL DEFAULT 'text',
                options TEXT DEFAULT '[]',
                is_required INTEGER DEFAULT 0,
                placeholder TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_templates (
                id TEXT PRIMARY KEY,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                icon TEXT DEFAULT '',
                section_ids TEXT DEFAULT '[]',
                is_enabled INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
```

- [ ] **Step 2: Add form_sections CRUD functions**

Append to end of `database.py`:

```python
# ---- Form Sections ----

def create_form_section(agency_id, title, description='', sort_order=0, is_enabled=1, is_default=0):
    section_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO form_sections (id, agency_id, title, description, sort_order, is_enabled, is_default, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (section_id, agency_id, title, description, sort_order, is_enabled, is_default, datetime.now().isoformat()),
        )
    return section_id


def list_form_sections(agency_id, enabled_only=False):
    with get_db() as conn:
        if enabled_only:
            rows = conn.execute(
                'SELECT * FROM form_sections WHERE agency_id = ? AND is_enabled = 1 ORDER BY sort_order',
                (agency_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM form_sections WHERE agency_id = ? ORDER BY sort_order',
                (agency_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_form_section(section_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM form_sections WHERE id = ?', (section_id,)).fetchone()
        return dict(row) if row else None


def update_form_section(section_id, **kwargs):
    allowed = {'title', 'description', 'sort_order', 'is_enabled'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [section_id]
    with get_db() as conn:
        conn.execute(f'UPDATE form_sections SET {set_clause} WHERE id = ?', values)


def delete_form_section(section_id):
    with get_db() as conn:
        conn.execute('DELETE FROM form_questions WHERE section_id = ?', (section_id,))
        conn.execute('DELETE FROM form_sections WHERE id = ?', (section_id,))
```

- [ ] **Step 3: Add form_questions CRUD functions**

Append to `database.py`:

```python
# ---- Form Questions ----

def create_form_question(section_id, agency_id, label, field_key, field_type='text', options='[]', is_required=0, placeholder='', sort_order=0):
    question_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO form_questions (id, section_id, agency_id, label, field_key, field_type, options, is_required, placeholder, sort_order, is_enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)',
            (question_id, section_id, agency_id, label, field_key, field_type, options, is_required, placeholder, sort_order, datetime.now().isoformat()),
        )
    return question_id


def list_form_questions(section_id, enabled_only=False):
    with get_db() as conn:
        if enabled_only:
            rows = conn.execute(
                'SELECT * FROM form_questions WHERE section_id = ? AND is_enabled = 1 ORDER BY sort_order',
                (section_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM form_questions WHERE section_id = ? ORDER BY sort_order',
                (section_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_form_question(question_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM form_questions WHERE id = ?', (question_id,)).fetchone()
        return dict(row) if row else None


def update_form_question(question_id, **kwargs):
    allowed = {'label', 'field_key', 'field_type', 'options', 'is_required', 'placeholder', 'sort_order', 'is_enabled'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [question_id]
    with get_db() as conn:
        conn.execute(f'UPDATE form_questions SET {set_clause} WHERE id = ?', values)


def delete_form_question(question_id):
    with get_db() as conn:
        conn.execute('DELETE FROM form_questions WHERE id = ?', (question_id,))
```

- [ ] **Step 4: Add document_templates CRUD functions**

Append to `database.py`:

```python
# ---- Document Templates ----

def create_document_template(agency_id, name, description='', icon='', section_ids='[]', is_enabled=1, is_default=0, sort_order=0):
    template_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO document_templates (id, agency_id, name, description, icon, section_ids, is_enabled, is_default, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (template_id, agency_id, name, description, icon, section_ids, is_enabled, is_default, sort_order, datetime.now().isoformat()),
        )
    return template_id


def list_document_templates(agency_id, enabled_only=False):
    with get_db() as conn:
        if enabled_only:
            rows = conn.execute(
                'SELECT * FROM document_templates WHERE agency_id = ? AND is_enabled = 1 ORDER BY sort_order',
                (agency_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM document_templates WHERE agency_id = ? ORDER BY sort_order',
                (agency_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_document_template(template_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM document_templates WHERE id = ?', (template_id,)).fetchone()
        return dict(row) if row else None


def update_document_template(template_id, **kwargs):
    allowed = {'name', 'description', 'icon', 'section_ids', 'is_enabled', 'sort_order'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [template_id]
    with get_db() as conn:
        conn.execute(f'UPDATE document_templates SET {set_clause} WHERE id = ?', values)


def delete_document_template(template_id):
    with get_db() as conn:
        conn.execute('DELETE FROM document_templates WHERE id = ?', (template_id,))
```

- [ ] **Step 5: Add `seed_agency_defaults()` function**

This is the large function that creates all 8 default sections with their questions and 10 default document templates. Append to `database.py`:

```python
# ---- Seed Defaults ----

def seed_agency_defaults(agency_id):
    """Seed default form sections, questions, and document templates for a new agency."""
    sections = {}

    # --- Section 1: Basic Information ---
    sid = create_form_section(agency_id, 'Basic Information', 'Tell us about your company', sort_order=1, is_default=1)
    sections['basic_info'] = sid
    questions_basic = [
        ('Company Name', 'full_name', 'text', '[]', 1, 'Acme Corp', 1),
        ('Email Address', 'email', 'email', '[]', 1, 'jane@acmecorp.com', 2),
        ('Phone Number', 'phone', 'phone', '[]', 0, '(555) 123-4567', 3),
        ('Website URL', 'website', 'url', '[]', 0, 'https://acmecorp.com', 4),
        ('Primary Contact Name', 'manager_name', 'text', '[]', 0, 'Jane Smith', 5),
    ]
    for label, key, ftype, opts, req, ph, order in questions_basic:
        create_form_question(sid, agency_id, label, key, ftype, opts, req, ph, order)

    # --- Section 2: Service Selection ---
    sid = create_form_section(agency_id, 'Service Selection', 'Choose the services you need', sort_order=2, is_default=1)
    sections['service_selection'] = sid
    create_form_question(sid, agency_id, 'Service Type', 'role', 'select',
        json.dumps(['Social Media', 'Content Marketing', 'Paid Ads', 'SEO', 'Branding']),
        1, 'Select a service...', 1)
    create_form_question(sid, agency_id, 'Start Date', 'start_date', 'date', '[]', 1, '', 2)
    create_form_question(sid, agency_id, 'Budget Range', 'budget', 'select',
        json.dumps(['Under $2k', '$2k-$5k', '$5k-$10k', '$10k-$25k', '$25k+']),
        0, 'Select budget range...', 3)
    create_form_question(sid, agency_id, 'Engagement Duration', 'duration', 'select',
        json.dumps(['1 Month', '3 Months', '6 Months', '12 Months', 'Ongoing']),
        0, 'Select duration...', 4)

    # --- Section 3: Business Overview ---
    sid = create_form_section(agency_id, 'Business Overview', 'Help us understand your business', sort_order=3, is_default=1)
    sections['business_overview'] = sid
    create_form_question(sid, agency_id, 'Business Description', 'business_description', 'textarea', '[]', 1, 'Describe your business and the services/products you offer...', 1)
    create_form_question(sid, agency_id, 'Target Market / Ideal Client', 'target_audience', 'textarea', '[]', 0, 'Who is your ideal customer? (demographics, industry, pain points)', 2)
    create_form_question(sid, agency_id, 'Key Differentiators', 'differentiators', 'textarea', '[]', 0, 'What sets you apart from competitors?', 3)

    # --- Section 4: Current Tools ---
    sid = create_form_section(agency_id, 'Current Tools', 'What tools does your business use?', sort_order=4, is_default=1)
    sections['current_tools'] = sid
    create_form_question(sid, agency_id, 'CRM / Contact Management', 'crm_tools', 'multiselect',
        json.dumps(['HubSpot', 'Salesforce', 'Pipedrive', 'Zoho', 'None', 'Other']),
        0, '', 1)
    create_form_question(sid, agency_id, 'Project / Task Management', 'pm_tools', 'multiselect',
        json.dumps(['ClickUp', 'Asana', 'Monday', 'Trello', 'Notion', 'None', 'Other']),
        0, '', 2)
    create_form_question(sid, agency_id, 'Email Marketing', 'email_tools', 'multiselect',
        json.dumps(['Mailchimp', 'ConvertKit', 'ActiveCampaign', 'Klaviyo', 'None', 'Other']),
        0, '', 3)
    create_form_question(sid, agency_id, 'Social Media Management', 'social_tools', 'multiselect',
        json.dumps(['Hootsuite', 'Buffer', 'Sprout Social', 'Later', 'None', 'Other']),
        0, '', 4)
    create_form_question(sid, agency_id, 'Analytics / Reporting', 'analytics_tools', 'multiselect',
        json.dumps(['Google Analytics', 'SEMrush', 'Ahrefs', 'None', 'Other']),
        0, '', 5)
    create_form_question(sid, agency_id, 'AI Tools', 'ai_tools', 'multiselect',
        json.dumps(['ChatGPT', 'Claude', 'Jasper', 'None', 'Other']),
        0, '', 6)

    # --- Section 5: Business Processes ---
    sid = create_form_section(agency_id, 'Business Processes', 'Tell us about your current workflows', sort_order=5, is_default=1)
    sections['business_processes'] = sid
    create_form_question(sid, agency_id, 'Lead Generation Process', 'lead_gen_process', 'textarea', '[]', 0, 'How do you currently generate leads?', 1)
    create_form_question(sid, agency_id, 'Client Onboarding Process', 'client_onboarding_process', 'textarea', '[]', 0, 'How do you onboard new clients?', 2)
    create_form_question(sid, agency_id, 'Service Delivery Process', 'service_delivery_process', 'textarea', '[]', 0, 'How do you deliver your services?', 3)
    create_form_question(sid, agency_id, 'Client Retention Process', 'client_retention_process', 'textarea', '[]', 0, 'How do you retain clients?', 4)

    # --- Section 6: Challenges & Goals ---
    sid = create_form_section(agency_id, 'Challenges & Goals', 'What are you trying to achieve?', sort_order=6, is_default=1)
    sections['challenges_goals'] = sid
    create_form_question(sid, agency_id, 'Top 3 Business Challenges', 'challenges', 'textarea', '[]', 1, 'What are your biggest business challenges right now?', 1)
    create_form_question(sid, agency_id, 'Manual / Repetitive Tasks', 'manual_tasks', 'textarea', '[]', 0, 'What tasks take up the most time in your business?', 2)
    create_form_question(sid, agency_id, '6-12 Month Business Goals', 'goals', 'textarea', '[]', 1, 'What do you want to achieve in the next 6-12 months?', 3)
    create_form_question(sid, agency_id, 'Success Metrics / KPIs', 'kpis', 'textarea', '[]', 0, 'How will you measure success?', 4)

    # --- Section 7: Project Specifics ---
    sid = create_form_section(agency_id, 'Project Specifics', 'Details about what you need', sort_order=7, is_default=1)
    sections['project_specifics'] = sid
    create_form_question(sid, agency_id, 'Specific Project or Solution Needed', 'project_needs', 'textarea', '[]', 0, 'What specific project or solution are you looking for?', 1)
    create_form_question(sid, agency_id, 'Ideal Timeline', 'timeline', 'select',
        json.dumps(['ASAP', '1-2 Weeks', '1 Month', '2-3 Months', 'Flexible']),
        0, 'Select timeline...', 2)
    create_form_question(sid, agency_id, 'Required Integrations', 'integrations', 'textarea', '[]', 0, 'Any tools or platforms that need to be integrated?', 3)

    # --- Section 8: Communication Preferences ---
    sid = create_form_section(agency_id, 'Communication Preferences', 'How should we stay in touch?', sort_order=8, is_default=1)
    sections['communication'] = sid
    create_form_question(sid, agency_id, 'Meeting Frequency', 'meeting_frequency', 'select',
        json.dumps(['Weekly', 'Bi-weekly', 'Monthly', 'As Needed']),
        0, 'Select frequency...', 1)
    create_form_question(sid, agency_id, 'Preferred Communication Tools', 'communication_tools', 'multiselect',
        json.dumps(['Email', 'Slack', 'Video Calls', 'Phone', 'WhatsApp']),
        0, '', 2)
    create_form_question(sid, agency_id, 'Availability Notes', 'availability_notes', 'textarea', '[]', 0, 'Best times to reach you, timezone, etc.', 3)

    # --- Document Templates ---
    templates = [
        ('Welcome Guide', 'Personalized welcome letter with onboarding timeline, team introductions, and what to expect in the first 30 days.', '\U0001f44b',
         [sections['basic_info'], sections['service_selection']], 1),
        ('Project Kickoff Guide', 'Day-1 guide with first-week activities, kickoff call agenda, and immediate action items.', '\U0001f5d3\ufe0f',
         [sections['basic_info'], sections['service_selection'], sections['project_specifics']], 2),
        ('90-Day Success Plan', 'Quarterly roadmap with weekly milestones, deliverables, and measurable targets.', '\U0001f4c5',
         [sections['service_selection'], sections['challenges_goals'], sections['project_specifics']], 3),
        ('Growth Blueprint', 'Comprehensive growth strategy based on business goals, market position, and competitive landscape.', '\U0001f680',
         [sections['business_overview'], sections['challenges_goals'], sections['current_tools']], 4),
        ('Competitor Analysis', 'Analysis of competitive landscape with strategic positioning recommendations.', '\U0001f50d',
         [sections['business_overview'], sections['challenges_goals']], 5),
        ('SOP System', 'Standard operating procedures for the client engagement workflows.', '\u2699\ufe0f',
         [sections['business_processes'], sections['current_tools'], sections['service_selection']], 6),
        ('Content Engine Blueprint', 'Content strategy with channels, formats, publishing cadence, and calendar framework.', '\u270f\ufe0f',
         [sections['business_overview'], sections['challenges_goals'], sections['current_tools']], 7),
        ('Technical Setup Plan', 'Implementation plan for tools, integrations, and technical infrastructure.', '\U0001f527',
         [sections['current_tools'], sections['project_specifics']], 8),
        ('Client Portal & Tools Guide', 'Guide to accessing the client dashboard, available tools, and resources.', '\U0001f6e0\ufe0f',
         [sections['basic_info'], sections['service_selection']], 9),
        ('Terms & Policies', 'Service terms, payment schedule, revision policy, and communication guidelines.', '\U0001f4cb',
         [sections['service_selection'], sections['communication']], 10),
    ]

    for name, desc, icon, sids, order in templates:
        create_document_template(agency_id, name, desc, icon, json.dumps(sids), is_enabled=1, is_default=1, sort_order=order)

    logger.info(f'Seeded defaults for agency {agency_id}')
```

- [ ] **Step 6: Add `backfill_existing_agencies()` function**

Append to `database.py`:

```python
def backfill_existing_agencies():
    """Seed defaults for any agency that has no form sections yet."""
    with get_db() as conn:
        agencies = conn.execute('SELECT id FROM agencies').fetchall()
    for row in agencies:
        agency_id = row['id']
        existing = list_form_sections(agency_id)
        if not existing:
            seed_agency_defaults(agency_id)
            logger.info(f'Backfilled defaults for agency {agency_id}')
```

- [ ] **Step 7: Add helper to get full form config for an agency**

Append to `database.py`:

```python
def get_agency_form_config(agency_id):
    """Return all enabled sections with their enabled questions, ordered."""
    sections = list_form_sections(agency_id, enabled_only=True)
    for section in sections:
        section['questions'] = list_form_questions(section['id'], enabled_only=True)
    return sections
```

- [ ] **Step 8: Verify tables created**

Run: `python3 -c "import database as db; db.init_db(); print('Tables created OK')"`
Expected: `Tables created OK`

- [ ] **Step 9: Commit**

```bash
git add database.py
git commit -m "feat: add form_sections, form_questions, document_templates tables with CRUD and seed defaults"
```

---

### Task 2: Add `generate_from_template()` to AI generator

**Files:**
- Modify: `services/ai_generator.py` — add new method after line 39

- [ ] **Step 1: Add the dynamic generation method**

Add after the `_generate_content` method (line 39) in `services/ai_generator.py`:

```python
    def generate_from_template(self, agency_name, template_name, template_description, client_answers):
        """Build a prompt dynamically from template description and client answers, then generate."""
        answers_text = ''
        for section_title, fields in client_answers.items():
            answers_text += f'\n## {section_title}\n'
            for label, value in fields.items():
                if value:
                    if isinstance(value, list):
                        value = ', '.join(str(v) for v in value)
                    answers_text += f'- {label}: {value}\n'

        prompt = f"""You are a specialist at {agency_name}. Create a {template_name} for this client.

DOCUMENT REQUIREMENTS:
{template_description}

CLIENT INFORMATION:
{answers_text}

Write in professional markdown with headers (##), bullet points, and bold text for emphasis.
Be specific to this client's situation — reference their actual business, goals, and challenges.
Keep the tone collaborative and results-oriented."""

        return self._generate_content(prompt, max_tokens=2500)
```

- [ ] **Step 2: Verify import works**

Run: `python3 -c "from services.ai_generator import AIGenerator; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add services/ai_generator.py
git commit -m "feat: add generate_from_template() for dynamic document generation"
```

---

### Task 3: Update validators for dynamic form fields

**Files:**
- Modify: `utils/validators.py`

- [ ] **Step 1: Replace the hardcoded `validate_onboarding_data()` with a dynamic version**

Replace the entire contents of `utils/validators.py` with:

```python
import re
from datetime import datetime


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_date(date_string):
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False


def validate_onboarding_data(data, required_fields=None):
    """Validate onboarding form data.

    If required_fields is provided (list of dicts with 'field_key' and 'field_type'),
    validate those dynamically. Otherwise fall back to legacy validation.
    """
    errors = []

    if required_fields:
        for field in required_fields:
            key = field['field_key']
            ftype = field['field_type']
            label = field.get('label', key)
            value = data.get(key, '')

            if isinstance(value, list):
                if not value:
                    errors.append(f'{label} is required.')
            elif isinstance(value, str):
                if not value.strip():
                    errors.append(f'{label} is required.')
            elif not value:
                errors.append(f'{label} is required.')

            # Type-specific validation
            if value and ftype == 'email' and isinstance(value, str) and not validate_email(value):
                errors.append(f'{label}: invalid email format.')
            if value and ftype == 'date' and isinstance(value, str) and not validate_date(value):
                errors.append(f'{label}: invalid date format. Use YYYY-MM-DD.')
    else:
        # Legacy fallback for backward compatibility
        if not data.get('full_name', '').strip():
            errors.append('Company name is required.')
        email = data.get('email', '')
        if not email.strip():
            errors.append('Email is required.')
        elif not validate_email(email):
            errors.append('Invalid email format.')
        role = data.get('role', '')
        if not role.strip():
            errors.append('Service selection is required.')
        start_date = data.get('start_date', '')
        if not start_date.strip():
            errors.append('Start date is required.')
        elif not validate_date(start_date):
            errors.append('Invalid date format. Use YYYY-MM-DD.')

    return (len(errors) == 0, errors)
```

- [ ] **Step 2: Verify**

Run: `python3 -c "from utils.validators import validate_onboarding_data; print(validate_onboarding_data({'full_name': 'Test', 'email': 'a@b.com', 'role': 'seo', 'start_date': '2026-01-01'}))"`
Expected: `(True, [])`

- [ ] **Step 3: Commit**

```bash
git add utils/validators.py
git commit -m "feat: support dynamic required field validation in validate_onboarding_data"
```

---

### Task 4: Wire up database seeding on app startup and agency creation

**Files:**
- Modify: `app.py:29-31` (after `db.init_db()`)
- Modify: `app.py:250-309` (registration route)

- [ ] **Step 1: Add backfill call after `db.init_db()` in `app.py`**

After `db.init_db()` on line 30, add:

```python
db.backfill_existing_agencies()
```

So lines 29-31 become:

```python
# Initialize database
db.init_db()
db.backfill_existing_agencies()
```

- [ ] **Step 2: Add `seed_agency_defaults()` call in the registration route**

In the `register()` route, after the agency is created via `db.create_agency(...)`, add a call to seed defaults. Find the line where `agency_id = db.create_agency(name, slug)` is called (inside the registration handler), and add `db.seed_agency_defaults(agency_id)` right after it.

Look for the registration route (around line 260-290). After `agency_id = db.create_agency(...)`:

```python
            db.seed_agency_defaults(agency_id)
```

- [ ] **Step 3: Verify startup works**

Run: `python3 -c "import app; print('Startup OK')"`
Expected: Should print startup logs and `Startup OK` without errors.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: seed form defaults on agency creation and backfill existing agencies"
```

---

### Task 5: Add admin routes for Onboarding Setup page

**Files:**
- Modify: `app.py` — add new routes after the `admin_client_detail` route (after line 454)

- [ ] **Step 1: Add the main onboarding setup GET route**

Add after the `admin_client_detail` route:

```python
@app.route('/admin/onboarding-setup')
@login_required
def admin_onboarding_setup():
    agency = get_current_agency()
    owner = get_current_owner()
    sections = db.list_form_sections(agency['id'])
    for section in sections:
        section['questions'] = db.list_form_questions(section['id'])
    templates = db.list_document_templates(agency['id'])
    # Parse section_ids JSON for display
    for t in templates:
        t['linked_sections'] = json.loads(t['section_ids']) if t['section_ids'] else []
    return render_template(
        'admin/onboarding_setup.html',
        agency=agency,
        owner=owner,
        sections=sections,
        templates=templates,
    )
```

Note: `import json` is already available in `database.py` but NOT in `app.py`. Add `import json` at the top of `app.py` with the other imports if not already present.

- [ ] **Step 2: Add section CRUD API routes**

```python
@app.route('/admin/api/sections', methods=['POST'])
@login_required
def api_create_section():
    agency = get_current_agency()
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': 'Title is required.'}), 400
    max_order = 0
    existing = db.list_form_sections(agency['id'])
    if existing:
        max_order = max(s['sort_order'] for s in existing)
    section_id = db.create_form_section(
        agency['id'],
        title=data['title'].strip(),
        description=data.get('description', '').strip(),
        sort_order=max_order + 1,
    )
    return jsonify({'success': True, 'id': section_id})


@app.route('/admin/api/sections/<section_id>', methods=['PUT'])
@login_required
def api_update_section(section_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data.'}), 400
    db.update_form_section(section_id, **data)
    return jsonify({'success': True})


@app.route('/admin/api/sections/<section_id>', methods=['DELETE'])
@login_required
def api_delete_section(section_id):
    section = db.get_form_section(section_id)
    if not section:
        return jsonify({'error': 'Not found.'}), 404
    if section['is_default']:
        return jsonify({'error': 'Cannot delete default sections. Disable them instead.'}), 400
    db.delete_form_section(section_id)
    return jsonify({'success': True})
```

- [ ] **Step 3: Add question CRUD API routes**

```python
@app.route('/admin/api/questions', methods=['POST'])
@login_required
def api_create_question():
    agency = get_current_agency()
    data = request.get_json()
    if not data or not data.get('label', '').strip() or not data.get('section_id'):
        return jsonify({'error': 'Label and section_id are required.'}), 400
    # Auto-generate field_key from label
    field_key = data.get('field_key', '')
    if not field_key:
        field_key = re.sub(r'[^a-z0-9]+', '_', data['label'].lower()).strip('_')
    max_order = 0
    existing = db.list_form_questions(data['section_id'])
    if existing:
        max_order = max(q['sort_order'] for q in existing)
    question_id = db.create_form_question(
        section_id=data['section_id'],
        agency_id=agency['id'],
        label=data['label'].strip(),
        field_key=field_key,
        field_type=data.get('field_type', 'text'),
        options=json.dumps(data.get('options', [])),
        is_required=1 if data.get('is_required') else 0,
        placeholder=data.get('placeholder', ''),
        sort_order=max_order + 1,
    )
    return jsonify({'success': True, 'id': question_id})


@app.route('/admin/api/questions/<question_id>', methods=['PUT'])
@login_required
def api_update_question(question_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data.'}), 400
    if 'options' in data and isinstance(data['options'], list):
        data['options'] = json.dumps(data['options'])
    db.update_form_question(question_id, **data)
    return jsonify({'success': True})


@app.route('/admin/api/questions/<question_id>', methods=['DELETE'])
@login_required
def api_delete_question(question_id):
    db.delete_form_question(question_id)
    return jsonify({'success': True})
```

- [ ] **Step 4: Add document template CRUD API routes**

```python
@app.route('/admin/api/templates', methods=['POST'])
@login_required
def api_create_template():
    agency = get_current_agency()
    data = request.get_json()
    if not data or not data.get('name', '').strip():
        return jsonify({'error': 'Name is required.'}), 400
    max_order = 0
    existing = db.list_document_templates(agency['id'])
    if existing:
        max_order = max(t['sort_order'] for t in existing)
    template_id = db.create_document_template(
        agency_id=agency['id'],
        name=data['name'].strip(),
        description=data.get('description', '').strip(),
        icon=data.get('icon', ''),
        section_ids=json.dumps(data.get('section_ids', [])),
        sort_order=max_order + 1,
    )
    return jsonify({'success': True, 'id': template_id})


@app.route('/admin/api/templates/<template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data.'}), 400
    if 'section_ids' in data and isinstance(data['section_ids'], list):
        data['section_ids'] = json.dumps(data['section_ids'])
    db.update_document_template(template_id, **data)
    return jsonify({'success': True})


@app.route('/admin/api/templates/<template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    tmpl = db.get_document_template(template_id)
    if not tmpl:
        return jsonify({'error': 'Not found.'}), 404
    if tmpl['is_default']:
        return jsonify({'error': 'Cannot delete default templates. Disable them instead.'}), 400
    db.delete_document_template(template_id)
    return jsonify({'success': True})


@app.route('/admin/api/sections/reorder', methods=['POST'])
@login_required
def api_reorder_sections():
    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'error': 'Missing order.'}), 400
    for i, section_id in enumerate(data['order']):
        db.update_form_section(section_id, sort_order=i + 1)
    return jsonify({'success': True})


@app.route('/admin/api/questions/reorder', methods=['POST'])
@login_required
def api_reorder_questions():
    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({'error': 'Missing order.'}), 400
    for i, question_id in enumerate(data['order']):
        db.update_form_question(question_id, sort_order=i + 1)
    return jsonify({'success': True})
```

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add admin API routes for form sections, questions, and document templates"
```

---

### Task 6: Modify `process_onboarding()` and `regenerate_documents()` to use dynamic templates

**Files:**
- Modify: `app.py:122-243` (`process_onboarding`)
- Modify: `app.py:798-850` (`regenerate_documents`)

- [ ] **Step 1: Replace the hardcoded document generation in `process_onboarding()`**

Replace lines 173-201 (the document generation block starting with `# 3. Generate AI documents`) with:

```python
        # 3. Generate AI documents from dynamic templates
        documents = []
        agency_id = store.get('agency_id', '')
        templates = db.list_document_templates(agency_id, enabled_only=True)

        for template in templates:
            content = ''
            if ai_generator:
                try:
                    # Gather client answers from linked sections
                    linked_section_ids = json.loads(template['section_ids']) if template['section_ids'] else []
                    client_answers = {}
                    for sec_id in linked_section_ids:
                        section = db.get_form_section(sec_id)
                        if not section:
                            continue
                        questions = db.list_form_questions(sec_id, enabled_only=True)
                        section_answers = {}
                        for q in questions:
                            val = data.get(q['field_key'], '')
                            if val:
                                section_answers[q['label']] = val
                        if section_answers:
                            client_answers[section['title']] = section_answers

                    content = ai_generator.generate_from_template(
                        agency_name=agency_name,
                        template_name=template['name'],
                        template_description=template['description'],
                        client_answers=client_answers,
                    )
                    logger.info(f'Generated {template["name"]} for {onboarding_id}')
                except Exception as e:
                    logger.error(f'AI generation error ({template["name"]}): {e}')
                    content = 'Document generation pending. Please check back later.'

            # Use template id as the doc type key for uniqueness
            doc_type_key = re.sub(r'[^a-z0-9]+', '_', template['name'].lower()).strip('_')
            documents.append({
                'type': doc_type_key,
                'title': template['name'],
                'icon': template['icon'],
                'content': content,
                'read': False,
            })

        store['documents'] = documents
```

Note: Add `import json` at the top of `app.py` if not already there.

- [ ] **Step 2: Replace the hardcoded document regeneration in `regenerate_documents()`**

Replace the `doc_types` list and `run_regeneration()` inner function (lines 812-848) with:

```python
    agency_id = record['agency_id']
    templates = db.list_document_templates(agency_id, enabled_only=True)

    def run_regeneration():
        try:
            documents = []
            for template in templates:
                content = ''
                try:
                    linked_section_ids = json.loads(template['section_ids']) if template['section_ids'] else []
                    client_answers = {}
                    for sec_id in linked_section_ids:
                        section = db.get_form_section(sec_id)
                        if not section:
                            continue
                        questions = db.list_form_questions(sec_id, enabled_only=True)
                        section_answers = {}
                        for q in questions:
                            val = data.get(q['field_key'], '')
                            if val:
                                section_answers[q['label']] = val
                        if section_answers:
                            client_answers[section['title']] = section_answers

                    content = ai_generator.generate_from_template(
                        agency_name=agency['name'],
                        template_name=template['name'],
                        template_description=template['description'],
                        client_answers=client_answers,
                    )
                    logger.info(f'Regenerated {template["name"]} for {onboarding_id}')
                except Exception as e:
                    logger.error(f'Regeneration error ({template["name"]}): {e}')
                    content = 'Document generation failed. Please try again later.'

                doc_type_key = re.sub(r'[^a-z0-9]+', '_', template['name'].lower()).strip('_')
                documents.append({
                    'type': doc_type_key,
                    'title': template['name'],
                    'icon': template['icon'],
                    'content': content,
                    'read': False,
                })

            data['documents'] = documents
            db.update_onboarding(onboarding_id, data=data)
            logger.info(f'Documents regenerated for {onboarding_id}')
        except Exception as e:
            logger.error(f'Regeneration failed for {onboarding_id}: {e}')
```

- [ ] **Step 3: Update the email sending block in `process_onboarding()`**

The email block (lines 204-228) currently maps specific doc types to specific email methods. Replace it with a generic approach that sends each document via a single method:

Replace:
```python
                for doc in documents:
                    if doc['content']:
                        email_methods = {
                            'welcome_guide': 'send_ai_welcome_guide',
                            'day1_guide': 'send_ai_day1_guide',
                            '90day_plan': 'send_ai_90day_plan',
                            'tools_access': 'send_ai_tools_access',
                            'terms_policies': 'send_ai_company_policies',
                        }
                        method = email_methods.get(doc['type'])
                        if method and hasattr(notification_service, method):
                            try:
                                getattr(notification_service, method)(data, doc['content'])
                            except Exception as e:
                                logger.error(f'Email error ({doc["type"]}): {e}')
```

With:
```python
                for doc in documents:
                    if doc['content']:
                        try:
                            notification_service.send_ai_document_email(data, doc['content'], doc['title'])
                        except Exception as e:
                            logger.error(f'Email error ({doc["title"]}): {e}')
```

Note: `send_ai_document_email` already exists in `notifications.py`. If it doesn't accept a `title` parameter, we'll update it in the next task. Check the method signature first.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: use dynamic document templates in process_onboarding and regenerate_documents"
```

---

### Task 7: Modify the onboarding form route and submission to be dynamic

**Files:**
- Modify: `app.py:461-524` (agency_onboard_form, agency_onboard, agency_demo routes)

- [ ] **Step 1: Update `agency_onboard_form()` to pass dynamic form config**

Replace:
```python
@app.route('/a/<slug>')
def agency_onboard_form(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    return render_template('index.html', agency=agency, agency_name=agency['name'])
```

With:
```python
@app.route('/a/<slug>')
def agency_onboard_form(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    form_config = db.get_agency_form_config(agency['id'])
    return render_template('index.html', agency=agency, agency_name=agency['name'], form_sections=form_config)
```

- [ ] **Step 2: Update `agency_onboard()` to use dynamic validation**

Replace the validation block in `agency_onboard()`:
```python
    is_valid, errors = validate_onboarding_data(data)
```

With:
```python
    # Build required fields list from dynamic form config
    form_config = db.get_agency_form_config(agency['id'])
    required_fields = []
    for section in form_config:
        for q in section['questions']:
            if q['is_required']:
                required_fields.append({'field_key': q['field_key'], 'field_type': q['field_type'], 'label': q['label']})
    is_valid, errors = validate_onboarding_data(data, required_fields=required_fields if required_fields else None)
```

- [ ] **Step 3: Update `agency_demo()` to include the expanded sample data**

Replace the `sample_data` dict in `agency_demo()` with:

```python
    sample_data = {
        'full_name': 'Acme Corp',
        'email': 'hello@acmecorp.com',
        'role': 'Social Media',
        'department': 'Technology',
        'start_date': datetime.now().strftime('%Y-%m-%d'),
        'manager_name': 'Jane Smith',
        'manager_email': 'jane@acmecorp.com',
        'phone': '555-0100',
        'website': 'https://acmecorp.com',
        'budget': '$5k-$10k',
        'duration': '6 Months',
        'business_description': 'Acme Corp is a B2B SaaS company providing project management tools for mid-size teams.',
        'target_audience': 'B2B SaaS companies, 50-500 employees, US-based.',
        'differentiators': 'AI-powered task prioritization and real-time collaboration features.',
        'challenges': 'Low social media engagement, inconsistent content publishing, poor lead generation from digital channels.',
        'goals': 'Increase brand awareness by 50% and generate 200 qualified leads per month within 6 months.',
        'kpis': 'Engagement rate, Lead generation, Website traffic, Conversion rate',
        'project_needs': 'Full social media management, content strategy, and paid advertising campaigns.',
        'communication_tools': ['Email', 'Video Calls'],
        'meeting_frequency': 'Weekly',
    }
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: dynamic form config in onboarding routes with dynamic validation"
```

---

### Task 8: Create the admin Onboarding Setup template

**Files:**
- Create: `templates/admin/onboarding_setup.html`

- [ ] **Step 1: Create the full template**

Create `templates/admin/onboarding_setup.html`. This is a large file — it follows the exact same sidebar layout as the existing `admin/dashboard.html`, with the agency branding, sidebar nav, and main content area. It has two tabs: Questions and Documents, both managed via JavaScript AJAX calls to the API routes created in Task 5.

The template should:
- Reuse the sidebar pattern from `admin/dashboard.html` (same sidebar brand, nav with links, footer)
- Add "Onboarding Setup" link to sidebar nav (with a `⚡` icon)
- Mark it as `.active` in the sidebar
- Tab content for Questions: list sections as collapsible cards, each with questions, add/edit/delete/toggle
- Tab content for Documents: list template cards, each with name/icon/description/linked sections, add/edit/delete/toggle
- All operations use `fetch()` to the `/admin/api/...` endpoints, then refresh the page on success

This is the longest single file. See the full template in the spec appendix below.

- [ ] **Step 2: Commit**

```bash
git add templates/admin/onboarding_setup.html
git commit -m "feat: add admin onboarding setup page template"
```

---

### Task 9: Add sidebar nav link to all admin templates

**Files:**
- Modify: `templates/admin/dashboard.html`
- Modify: `templates/admin/settings.html`
- Modify: `templates/admin/meetings.html`
- Modify: `templates/admin/mail.html`
- Modify: `templates/admin/client_detail.html`

- [ ] **Step 1: Add the Onboarding Setup nav link to all admin templates**

In each admin template, find the `<nav class="sidebar-nav">` block and add this link before the Settings link:

```html
        <a href="{{ url_for('admin_onboarding_setup') }}">
            <span class="nav-icon">⚡</span> Onboarding Setup
        </a>
```

The sidebar nav block should become (using `dashboard.html` as example):

```html
    <nav class="sidebar-nav">
        <a href="{{ url_for('admin_dashboard') }}" class="active">
            <span class="nav-icon">◉</span> Clients
        </a>
        <a href="{{ url_for('admin_meetings') }}">
            <span class="nav-icon">☷</span> Meetings
            {% if pending_meetings %}<span class="nav-badge">{{ pending_meetings }}</span>{% endif %}
        </a>
        <a href="{{ url_for('admin_mail') }}">
            <span class="nav-icon">✉</span> Mail
        </a>
        <a href="{{ url_for('admin_onboarding_setup') }}">
            <span class="nav-icon">⚡</span> Onboarding Setup
        </a>
        <a href="{{ url_for('admin_settings') }}">
            <span class="nav-icon">⚙</span> Settings
        </a>
    </nav>
```

Do this for all 5 admin templates. In each template, set the `class="active"` only on the current page's link.

- [ ] **Step 2: Commit**

```bash
git add templates/admin/
git commit -m "feat: add Onboarding Setup link to all admin sidebar navs"
```

---

### Task 10: Rewrite `index.html` to render form dynamically

**Files:**
- Rewrite: `templates/index.html`

- [ ] **Step 1: Replace hardcoded steps with dynamic Jinja2 rendering**

Replace the entire `index.html` with a template that:
- Step 1 is still the Welcome screen (hardcoded — uses agency branding)
- Steps 2 through N are dynamically generated from `form_sections` (passed as Jinja2 variable)
- Each section becomes one step, with its questions rendered by `field_type`:
  - `text`, `email`, `phone`, `url` → `<input type="...">`
  - `textarea` → `<textarea>`
  - `date` → `<input type="date">`
  - `select` → `<select>` with options parsed from JSON
  - `multiselect` → chip-style toggleable buttons (like current communication tools)
  - `checkbox` → `<input type="checkbox">`
- Final step (N+1) is the Success screen (hardcoded)
- Passes `form_sections` to JavaScript as JSON for validation and collection

Key Jinja2 loop:

```html
{% for section in form_sections %}
<div class="step-screen" id="step-{{ loop.index + 1 }}">
    <div class="info-card">
        <h2>{{ section.title }}</h2>
        <p class="subtitle">{{ section.description }}</p>

        {% for q in section.questions %}
        <div class="form-group">
            <label>{{ q.label }}{% if q.is_required %} <span class="required">*</span>{% endif %}</label>

            {% if q.field_type == 'textarea' %}
            <textarea class="modern-input" data-field="{{ q.field_key }}" placeholder="{{ q.placeholder }}"></textarea>

            {% elif q.field_type == 'select' %}
            <select class="modern-input" data-field="{{ q.field_key }}">
                <option value="">{{ q.placeholder or 'Select...' }}</option>
                {% for opt in q.options | tojson | from_json %}
                <option value="{{ opt }}">{{ opt }}</option>
                {% endfor %}
            </select>

            {% elif q.field_type == 'multiselect' %}
            <div class="chip-group" data-field="{{ q.field_key }}">
                {% for opt in q.options | tojson | from_json %}
                <div class="tool-chip" onclick="toggleChip(this, '{{ q.field_key }}', '{{ opt }}')">{{ opt }}</div>
                {% endfor %}
            </div>

            {% else %}
            <input type="{{ q.field_type }}" class="modern-input" data-field="{{ q.field_key }}" placeholder="{{ q.placeholder }}">
            {% endif %}
        </div>
        {% endfor %}

        <div class="btn-group">
            <button class="btn-back-modern" onclick="prevStep()">← Back</button>
            <button class="btn-continue" onclick="nextStep()">Continue →</button>
        </div>
    </div>
</div>
{% endfor %}
```

The template must also pass form metadata to JS:

```html
<script>
    const AGENCY_SLUG = {{ (agency.slug if agency else '')|tojson }};
    const FORM_SECTIONS = {{ form_sections|tojson }};
    const TOTAL_STEPS = FORM_SECTIONS.length + 1;
</script>
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: rewrite index.html to render dynamic form sections and questions"
```

---

### Task 11: Rewrite `modern-app.js` for dynamic form handling

**Files:**
- Rewrite: `static/js/modern-app.js`

- [ ] **Step 1: Replace hardcoded form logic with dynamic handling**

Replace the entire `modern-app.js` with:

```javascript
// Dynamic form state
const multiSelections = {};  // field_key -> Set of selected values
let currentStep = 1;

function goToStep(step) {
    document.querySelectorAll('.step-screen').forEach(s => s.classList.remove('active'));
    const target = document.getElementById(`step-${step}`);
    if (target) {
        target.classList.add('active');
        currentStep = step;
        updateProgress();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function nextStep() {
    if (validateStep(currentStep)) {
        goToStep(currentStep + 1);
    }
}

function prevStep() {
    if (currentStep > 1) {
        goToStep(currentStep - 1);
    }
}

function updateProgress() {
    const total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
    const progress = ((currentStep - 1) / total) * 100;
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = progress + '%';

    const indicator = document.getElementById('step-indicator');
    if (indicator && currentStep > 1 && currentStep <= total) {
        indicator.textContent = `Step ${currentStep - 1} of ${total}`;
        indicator.style.display = 'block';
    } else if (indicator) {
        indicator.style.display = 'none';
    }
}

function validateStep(step) {
    // Step 1 is welcome — no validation
    if (step === 1) return true;

    // Last step + 1 is success — no validation
    const total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
    if (step > total) return true;

    // Clear previous errors
    document.querySelectorAll(`#step-${step} .modern-input.error`).forEach(el => el.classList.remove('error'));
    document.querySelectorAll(`#step-${step} .error-message`).forEach(el => el.classList.remove('visible'));

    let valid = true;

    // Get the section index (step - 2 because step 1 is welcome)
    const sectionIndex = step - 2;
    if (typeof FORM_SECTIONS !== 'undefined' && FORM_SECTIONS[sectionIndex]) {
        const section = FORM_SECTIONS[sectionIndex];
        section.questions.forEach(q => {
            if (q.is_required) {
                if (q.field_type === 'multiselect') {
                    const sel = multiSelections[q.field_key];
                    if (!sel || sel.size === 0) {
                        // Show error on chip group
                        const group = document.querySelector(`[data-field="${q.field_key}"]`);
                        if (group) showFieldError(group, `${q.label} is required`);
                        valid = false;
                    }
                } else {
                    const el = document.querySelector(`[data-field="${q.field_key}"]`);
                    if (el && !el.value.trim()) {
                        markError(el, `${q.label} is required`);
                        valid = false;
                    }
                }
            }
            // Email validation
            if (q.field_type === 'email') {
                const el = document.querySelector(`[data-field="${q.field_key}"]`);
                if (el && el.value.trim() && !isValidEmail(el.value)) {
                    markError(el, 'Please enter a valid email address');
                    valid = false;
                }
            }
        });
    }

    return valid;
}

function markError(el, message) {
    el.classList.add('error');
    let errMsg = el.parentElement.querySelector('.error-message');
    if (!errMsg) {
        errMsg = document.createElement('div');
        errMsg.className = 'error-message';
        el.parentElement.appendChild(errMsg);
    }
    errMsg.textContent = message;
    errMsg.classList.add('visible');
}

function showFieldError(el, message) {
    let errMsg = el.parentElement.querySelector('.error-message');
    if (!errMsg) {
        errMsg = document.createElement('div');
        errMsg.className = 'error-message';
        el.parentElement.appendChild(errMsg);
    }
    errMsg.textContent = message;
    errMsg.classList.add('visible');
}

function isValidEmail(email) {
    return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email);
}

// Multiselect chip toggle
function toggleChip(chip, fieldKey, value) {
    if (!multiSelections[fieldKey]) {
        multiSelections[fieldKey] = new Set();
    }
    if (multiSelections[fieldKey].has(value)) {
        multiSelections[fieldKey].delete(value);
        chip.classList.remove('selected');
    } else {
        multiSelections[fieldKey].add(value);
        chip.classList.add('selected');
    }
}

function collectFormData() {
    const data = {};
    // Collect all inputs and textareas with data-field attribute
    document.querySelectorAll('[data-field]').forEach(el => {
        const key = el.dataset.field;
        if (el.classList.contains('chip-group')) {
            // multiselect — handled separately
            return;
        }
        if (el.type === 'checkbox') {
            data[key] = el.checked;
        } else {
            data[key] = el.value.trim();
        }
    });
    // Add multiselect values
    for (const [key, valueSet] of Object.entries(multiSelections)) {
        data[key] = Array.from(valueSet);
    }
    return data;
}

function getBaseUrl() {
    return typeof AGENCY_SLUG !== 'undefined' && AGENCY_SLUG ? `/a/${AGENCY_SLUG}` : '';
}

async function submitForm() {
    const data = collectFormData();
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');

    try {
        const response = await fetch(`${getBaseUrl()}/onboard`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });

        const result = await response.json();
        if (overlay) overlay.classList.add('hidden');

        if (result.success) {
            const idDisplay = document.getElementById('onboarding-id-display');
            if (idDisplay) idDisplay.textContent = result.onboarding_id;
            const dashLink = document.getElementById('dashboard-link');
            if (dashLink) dashLink.href = result.dashboard_url;
            showCredentials(data.email, result.client_password);

            const total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
            goToStep(total + 1);
            if (typeof launchConfetti === 'function') launchConfetti(100);
        } else {
            alert('Error: ' + (result.errors || []).join('\n'));
        }
    } catch (err) {
        if (overlay) overlay.classList.add('hidden');
        alert('An error occurred. Please try again.');
        console.error(err);
    }
}

function showCredentials(email, password) {
    const box = document.getElementById('credentials-box');
    const credEmail = document.getElementById('cred-email');
    const credPassword = document.getElementById('cred-password');
    if (box && credEmail && credPassword && password) {
        credEmail.textContent = email;
        credPassword.textContent = password;
        box.style.display = 'block';
    }
}

async function submitDemo() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');

    try {
        const response = await fetch(`${getBaseUrl()}/demo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const result = await response.json();
        if (overlay) overlay.classList.add('hidden');

        if (result.success) {
            const idDisplay = document.getElementById('onboarding-id-display');
            if (idDisplay) idDisplay.textContent = result.onboarding_id;
            const dashLink = document.getElementById('dashboard-link');
            if (dashLink) dashLink.href = result.dashboard_url;
            showCredentials('hello@acmecorp.com', result.client_password);

            const total = (typeof TOTAL_STEPS !== 'undefined') ? TOTAL_STEPS : 9;
            goToStep(total + 1);
            if (typeof launchConfetti === 'function') launchConfetti(100);
        } else {
            alert('Error: ' + (result.errors || []).join('\n'));
        }
    } catch (err) {
        if (overlay) overlay.classList.add('hidden');
        alert('An error occurred. Please try again.');
        console.error(err);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    goToStep(1);
});
```

- [ ] **Step 2: Commit**

```bash
git add static/js/modern-app.js
git commit -m "feat: rewrite modern-app.js for dynamic form sections, validation, and collection"
```

---

### Task 12: Verify end-to-end flow

**Files:** None (verification only)

- [ ] **Step 1: Start the app**

Run: `python3 app.py`
Expected: App starts on port 5050 with logs showing database initialization and backfill.

- [ ] **Step 2: Verify admin onboarding setup page loads**

Visit: `http://localhost:5050/admin/onboarding-setup` (after logging in)
Expected: Page loads with 8 default sections in Questions tab and 10 default templates in Documents tab.

- [ ] **Step 3: Verify dynamic onboarding form renders**

Visit: `http://localhost:5050/a/<your-agency-slug>`
Expected: Welcome screen loads, clicking "Get started" shows dynamic form steps matching the 8 default sections.

- [ ] **Step 4: Verify demo submission works**

Click "Try with sample data" on the onboarding form.
Expected: Onboarding submits successfully, shows credentials, documents begin generating in background.

- [ ] **Step 5: Verify admin can toggle a section and it disappears from form**

In admin Onboarding Setup, disable "Current Tools" section. Refresh the client form.
Expected: "Current Tools" step no longer appears in the form.

- [ ] **Step 6: Verify admin can add a custom document template**

In admin Onboarding Setup Documents tab, add a new template "Custom Report" with description and linked sections.
Expected: Template appears in the list. New onboardings generate this document.

- [ ] **Step 7: Commit final state**

```bash
git add -A
git commit -m "feat: dynamic onboarding form builder and document generation system"
```
