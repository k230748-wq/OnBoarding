# Dynamic Onboarding Form Builder + Document Generation

## Summary

Agency owners get an "Onboarding Setup" page in admin where they configure what questions clients answer and what AI documents get generated from those answers. New agencies get pre-loaded defaults so they work out of the box.

The system replaces hardcoded form fields and hardcoded document types with a fully dynamic, per-agency configuration stored in the database.

## Data Model

### `form_sections` table

Groups of questions (e.g., "Business Overview", "Current Tools").

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT (UUID) | Primary key |
| agency_id | TEXT | FK to agencies |
| title | TEXT | Section name |
| description | TEXT | Helper text shown to client |
| sort_order | INTEGER | Display order |
| is_enabled | INTEGER | 1=show, 0=skip |
| is_default | INTEGER | 1=shipped with system, 0=custom |
| created_at | TEXT | Timestamp |

### `form_questions` table

Individual questions within a section.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT (UUID) | Primary key |
| section_id | TEXT | FK to form_sections |
| agency_id | TEXT | FK to agencies |
| label | TEXT | Question text shown to client |
| field_key | TEXT | Machine key (e.g., `business_description`) |
| field_type | TEXT | text, textarea, select, multiselect, checkbox, date, email, phone, url |
| options | TEXT (JSON) | Choices for select/multiselect (JSON array of strings) |
| is_required | INTEGER | Validation flag |
| placeholder | TEXT | Input placeholder |
| sort_order | INTEGER | Order within section |
| is_enabled | INTEGER | 1=show, 0=skip |
| created_at | TEXT | Timestamp |

### `document_templates` table

Documents the AI should generate per onboarding.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT (UUID) | Primary key |
| agency_id | TEXT | FK to agencies |
| name | TEXT | e.g., "Growth Blueprint" |
| description | TEXT | What the owner wants in this doc (used to build AI prompt) |
| icon | TEXT | Emoji for dashboard display |
| section_ids | TEXT (JSON) | Which form_sections feed into this doc (JSON array of section IDs) |
| is_enabled | INTEGER | 1=generate, 0=skip |
| is_default | INTEGER | 1=shipped, 0=custom |
| sort_order | INTEGER | Generation order |
| created_at | TEXT | Timestamp |

## Pre-loaded Defaults

Seeded when a new agency is created (called from `create_agency()` or a dedicated `seed_agency_defaults(agency_id)` function).

### Default Sections & Questions

**1. Basic Information**
- Company name (text, required)
- Email (email, required)
- Phone (phone)
- Website (url)
- Primary contact name (text)

**2. Service Selection**
- Service type (select: social_media, content_marketing, paid_ads, seo, branding — required)
- Start date (date, required)
- Budget range (select: <$1k, $1k-$5k, $5k-$10k, $10k-$25k, $25k+)
- Engagement duration (select: 1_month, 3_months, 6_months, 12_months, ongoing)

**3. Business Overview**
- Business description (textarea, required)
- Target market / ideal client (textarea)
- Key differentiators from competitors (textarea)

**4. Current Tools**
- CRM / Contact Management (multiselect: HubSpot, Salesforce, Pipedrive, Zoho, None, Other)
- Project / Task Management (multiselect: ClickUp, Asana, Monday, Trello, Notion, None, Other)
- Email Marketing (multiselect: Mailchimp, ConvertKit, ActiveCampaign, Klaviyo, None, Other)
- Social Media Management (multiselect: Hootsuite, Buffer, Sprout Social, Later, None, Other)
- Analytics / Reporting (multiselect: Google Analytics, SEMrush, Ahrefs, None, Other)
- AI Tools (multiselect: ChatGPT, Claude, Jasper, None, Other)

**5. Business Processes**
- Lead generation process (textarea)
- Client onboarding process (textarea)
- Service delivery process (textarea)
- Client retention process (textarea)

**6. Challenges & Goals**
- Top 3 business challenges (textarea, required)
- Manual or repetitive tasks taking most time (textarea)
- 6-12 month business goals (textarea, required)
- Success metrics / KPIs (textarea)

**7. Project Specifics**
- Specific project or solution needed (textarea)
- Ideal implementation timeline (select: ASAP, 1-2 weeks, 1 month, 2-3 months, flexible)
- Required tool integrations (textarea)
- Key performance indicators (textarea)

**8. Communication Preferences**
- Preferred meeting frequency (select: weekly, biweekly, monthly, as_needed)
- Preferred communication tools (multiselect: email, slack, video_calls, phone, whatsapp)
- Availability notes (textarea)

### Default Document Templates

1. **Welcome Guide** (icon: wave) — "Personalized welcome letter with onboarding timeline, team introductions, and what to expect in the first 30 days." Feeds from: Basic Information, Service Selection.

2. **Project Kickoff Guide** (icon: calendar) — "Day-1 guide with first-week activities, kickoff call agenda, and immediate action items." Feeds from: Basic Information, Service Selection, Project Specifics.

3. **90-Day Success Plan** (icon: chart) — "Quarterly roadmap with weekly milestones, deliverables, and measurable targets." Feeds from: Service Selection, Challenges & Goals, Project Specifics.

4. **Growth Blueprint** (icon: rocket) — "Comprehensive growth strategy based on business goals, market position, and competitive landscape." Feeds from: Business Overview, Challenges & Goals, Current Tools.

5. **Competitor Analysis** (icon: magnifying glass) — "Analysis of competitive landscape with strategic positioning recommendations." Feeds from: Business Overview, Challenges & Goals.

6. **SOP System** (icon: gear) — "Standard operating procedures for the client engagement workflows." Feeds from: Business Processes, Current Tools, Service Selection.

7. **Content Engine Blueprint** (icon: pencil) — "Content strategy with channels, formats, publishing cadence, and calendar framework." Feeds from: Business Overview, Challenges & Goals, Current Tools.

8. **Technical Setup Plan** (icon: wrench) — "Implementation plan for tools, integrations, and technical infrastructure." Feeds from: Current Tools, Project Specifics.

9. **Client Portal & Tools Guide** (icon: tools) — "Guide to accessing the client dashboard, available tools, and resources." Feeds from: Basic Information, Service Selection.

10. **Terms & Policies** (icon: clipboard) — "Service terms, payment schedule, revision policy, and communication guidelines." Feeds from: Service Selection, Communication Preferences.

## AI Prompt Building

When a client submits the onboarding form, for each enabled document template the system:

1. Looks up `section_ids` on the template
2. Gathers all client answers from questions belonging to those sections
3. Builds a prompt:

```
You are a specialist at {agency_name}. Create a {document_name} for this client.

DOCUMENT REQUIREMENTS:
{document_template.description}

CLIENT INFORMATION:
{for each linked section}
## {section.title}
- {question.label}: {client's answer}
{end for}

Write in professional markdown with headers (##), bullet points, and bold text for emphasis.
Be specific to this client's situation — reference their actual business, goals, and challenges.
Keep the tone collaborative and results-oriented.
```

The owner never writes prompts — they describe what they want and pick which sections feed in. The system assembles the prompt automatically.

## Admin UI: Onboarding Setup Page

New route: `GET /admin/onboarding-setup`

### Questions Tab

- List of sections as collapsible cards, ordered by `sort_order`
- Each section card shows: title, description, question count, enable/disable toggle
- Expand a section to see its questions
- Each question row shows: label, field type badge, required badge, enable/disable toggle
- "Edit" button on each question opens inline editing (label, type, options, required, placeholder)
- "Add Question" button within each section
- "Add Section" button at bottom of the list
- Drag handles on sections and questions for reordering (or up/down buttons)
- Default sections show a "default" badge and cannot be deleted (only disabled)
- Custom sections can be deleted

### Documents Tab

- List of document template cards, ordered by `sort_order`
- Each card shows: icon, name, description (truncated), linked section names as tags, enable/disable toggle
- "Add Document" button at top
- Click a card to edit: name, icon (emoji picker or text input), description (textarea), linked sections (checkbox list of enabled sections)
- Default templates show a "default" badge and cannot be deleted (only disabled)
- Custom templates can be deleted

## Client-Facing Form Changes

`templates/index.html` becomes dynamic:

- The route `GET /a/<slug>` fetches enabled sections + questions for this agency from the database
- Passes them to the template as structured data
- Template renders one form step per section
- Each step renders questions based on `field_type`:
  - text, email, phone, url -> `<input type="...">`
  - textarea -> `<textarea>`
  - date -> `<input type="date">`
  - select -> `<select>` with options from `options` JSON
  - multiselect -> checkboxes or multi-select
  - checkbox -> single checkbox
- Client-side validation based on `is_required`
- On submit, sends all answers as JSON keyed by `field_key`

## Document Generation Changes

`process_onboarding()` changes:

- Fetches all enabled `document_templates` for the agency
- For each template:
  - Gathers client answers from linked sections
  - Builds prompt using the template method described above
  - Calls `ai_generator.generate_from_template(agency_name, template, client_answers)`
  - Stores result in the onboarding documents list
- All downstream features (dashboard document viewer, PDF download, email sending) continue to work since they read from the stored documents list — the document structure remains `{type, title, icon, content}`

## Changes to Existing Code

| File | Change |
|------|--------|
| `database.py` | Add 3 new tables (`form_sections`, `form_questions`, `document_templates`) + CRUD functions + `seed_agency_defaults(agency_id)` function |
| `app.py` | Add admin routes for onboarding setup page (GET + POST endpoints for sections, questions, templates). Modify `agency_onboard_form()` to fetch dynamic sections/questions. Modify `agency_onboard()` to accept dynamic fields. Modify `process_onboarding()` to use dynamic document templates. |
| `services/ai_generator.py` | Add `generate_from_template(agency_name, template_name, template_description, client_answers)` method that builds and executes the dynamic prompt |
| `templates/admin/onboarding_setup.html` | New template — setup page with Questions and Documents tabs |
| `templates/index.html` | Modify — render form dynamically from sections/questions data instead of hardcoded steps |
| `utils/validators.py` | Modify — `validate_onboarding_data()` accepts dynamic required fields list instead of hardcoded checks |

## Migration Path

Existing agencies (already in the database) need defaults seeded. On app startup, after `init_db()`, check each agency — if it has no `form_sections`, run `seed_agency_defaults(agency_id)`. This is a one-time backfill.

## What Does NOT Change

- Authentication flows (owner + client)
- Client dashboard structure (overview, documents, tools, meetings tabs)
- Document viewer, PDF download, email sending
- AI tools (content calendar, competitor analysis, etc.)
- ClickUp / Airtable integrations
- Meeting request system
- Agency branding / settings page
