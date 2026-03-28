import functools
import hashlib
import html as html_module
import json
import os
import re
import threading
from datetime import datetime

from dotenv import load_dotenv
from flask import (
    Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for,
)

import database as db
from services.ai_generator import AIGenerator
from services.airtable_service import get_airtable_for_agency
from services.clickup import ClickUpService
from services.notifications import NotificationService
from utils.logger import setup_logger
from utils.validators import validate_onboarding_data

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

logger = setup_logger()

# Initialize database
db.init_db()
db.migrate_agencies_table()
db.backfill_existing_agencies()

# Service role/service configurations
ROLE_CONFIGS = {
    'social_media': {
        'folder_templates': ['Content Calendar', 'Social Assets', 'Analytics Reports'],
        'default_tasks': ['Social audit', 'Content strategy session', 'First month calendar'],
    },
    'content_marketing': {
        'folder_templates': ['Blog Posts', 'Whitepapers', 'Content Calendar'],
        'default_tasks': ['Content audit', 'SEO keyword research', 'First blog assignment'],
    },
    'paid_ads': {
        'folder_templates': ['Ad Creatives', 'Campaign Reports', 'Audience Research'],
        'default_tasks': ['Platform setup', 'Pixel installation', 'First campaign launch'],
    },
    'seo': {
        'folder_templates': ['Technical Audits', 'Keyword Research', 'Backlink Reports'],
        'default_tasks': ['Technical SEO audit', 'Keyword strategy', 'First optimization round'],
    },
    'branding': {
        'folder_templates': ['Brand Guidelines', 'Logo Files', 'Visual Assets'],
        'default_tasks': ['Brand discovery session', 'Mood board creation', 'First concepts'],
    },
}

# Initialize services (fail gracefully)
ai_generator = None
notification_service = None
clickup_service = None

try:
    ai_generator = AIGenerator()
    logger.info('AI Generator initialized.')
except Exception as e:
    logger.warning(f'AI Generator unavailable: {e}')

try:
    notification_service = NotificationService()
    logger.info('Notification service initialized.')
except Exception as e:
    logger.warning(f'Notification service unavailable: {e}')

try:
    clickup_service = ClickUpService()
    logger.info('ClickUp service initialized.')
except Exception as e:
    logger.warning(f'ClickUp service unavailable: {e}')

# Airtable is now per-agency (configured in admin settings), not global


# ──────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if 'owner_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped


def get_current_owner():
    owner_id = session.get('owner_id')
    if not owner_id:
        return None
    return db.get_owner_by_id(owner_id)


def get_current_agency():
    owner = get_current_owner()
    if not owner:
        return None
    return db.get_agency_by_id(owner['agency_id'])


# ──────────────────────────────────────
# Background processing
# ──────────────────────────────────────

def process_onboarding(onboarding_id, data, agency_name, dashboard_url=''):
    """Background processing of onboarding workflow."""
    try:
        logger.info(f'Starting background processing for {onboarding_id}')

        record = db.get_onboarding(onboarding_id)
        if not record:
            logger.error(f'Onboarding record not found: {onboarding_id}')
            return

        store = record['data']
        role_config = ROLE_CONFIGS.get(data['role'], {})

        # 1. Create ClickUp tasks
        if clickup_service:
            try:
                result = clickup_service.create_onboarding_tasks(
                    client_name=data['full_name'],
                    service_type=data['role'],
                    start_date=data['start_date'],
                    contact_name=data.get('manager_name', data['full_name']),
                    custom_tasks=role_config.get('default_tasks'),
                )
                store['clickup_list_id'] = result.get('list_id')
                store['clickup_list_url'] = result.get('list_url', '')
                store['tasks_created'] = result.get('tasks_created', 0)
                logger.info(f'ClickUp tasks created for {onboarding_id}')
            except Exception as e:
                logger.error(f'ClickUp error for {onboarding_id}: {e}')
        else:
            store['tasks_created'] = 0

        # 2. Create Airtable record
        # 2. Sync to Airtable (per-agency config)
        agency_record = db.get_agency_by_id(store.get('agency_id', ''))
        airtable_svc = get_airtable_for_agency(agency_record) if agency_record else None
        if airtable_svc:
            try:
                airtable_result = airtable_svc.sync_client_record(store, onboarding_id)
                if airtable_result:
                    store['airtable_record_id'] = airtable_result.get('id', '')
                logger.info(f'Airtable record created for {onboarding_id}')
            except Exception as e:
                logger.error(f'Airtable error for {onboarding_id}: {e}')

        # 3. Generate AI documents from dynamic templates
        documents = []
        agency_id = store.get('agency_id', '')
        templates = db.list_document_templates(agency_id, enabled_only=True)

        for template in templates:
            content = ''
            if ai_generator:
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
                        agency_name=agency_name,
                        template_name=template['name'],
                        template_description=template['description'],
                        client_answers=client_answers,
                    )
                    logger.info(f'Generated {template["name"]} for {onboarding_id}')
                except Exception as e:
                    logger.error(f'AI generation error ({template["name"]}): {e}')
                    content = 'Document generation pending. Please check back later.'

            doc_type_key = re.sub(r'[^a-z0-9]+', '_', template['name'].lower()).strip('_')
            documents.append({
                'type': doc_type_key,
                'title': template['name'],
                'icon': template['icon'],
                'content': content,
                'read': False,
            })

        store['documents'] = documents

        # 4. Send emails — prefer per-agency SMTP, fall back to global
        if notification_service:
            try:
                notification_service.send_employee_welcome_email(data, onboarding_id, dashboard_url=dashboard_url)
                logger.info(f'Welcome email sent for {onboarding_id}')

                if data.get('manager_email'):
                    notification_service.send_manager_notification(data, onboarding_id, dashboard_url=dashboard_url)

                for doc in documents:
                    if doc['content']:
                        try:
                            notification_service.send_ai_document_email(data, doc['content'], doc_title=doc['title'])
                        except Exception as e:
                            logger.error(f'Email error ({doc["title"]}): {e}')
            except Exception as e:
                logger.error(f'Email error for {onboarding_id}: {e}')

        store['status'] = 'completed'
        store['completion_time'] = datetime.now().isoformat()
        db.update_onboarding(onboarding_id, data=store, status='completed')
        logger.info(f'Onboarding completed for {onboarding_id}')

        # Update Airtable status to Active + document count
        if airtable_svc:
            try:
                airtable_svc.update_client_status(onboarding_id, 'Active', doc_count=len(documents))
            except Exception as e:
                logger.error(f'Airtable status update error: {e}')

    except Exception as e:
        logger.error(f'Onboarding failed for {onboarding_id}: {e}')
        db.update_onboarding(onboarding_id, status='failed')

        if notification_service:
            try:
                notification_service.send_admin_alert(onboarding_id, str(e))
            except Exception:
                pass


# ──────────────────────────────────────
# Public routes — Landing page
# ──────────────────────────────────────

@app.route('/')
def home():
    return render_template('home.html')


# ──────────────────────────────────────
# Auth routes
# ──────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('auth/register.html')

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    agency_name = request.form.get('agency_name', '').strip()
    invite_code = request.form.get('invite_code', '').strip()

    errors = []
    if not name:
        errors.append('Name is required.')
    if not email:
        errors.append('Email is required.')
    if not password or len(password) < 6:
        errors.append('Password must be at least 6 characters.')
    if not agency_name:
        errors.append('Agency name is required.')
    if not invite_code:
        errors.append('Invite code is required.')

    if errors:
        return render_template('auth/register.html', errors=errors, name=name, email=email, agency_name=agency_name)

    # Validate invite code
    invite = db.get_invite_code(invite_code)
    if not invite or invite['is_used']:
        return render_template('auth/register.html', errors=['Invalid or already used invite code.'], name=name, email=email, agency_name=agency_name)

    # Check duplicate email
    if db.get_owner_by_email(email):
        return render_template('auth/register.html', errors=['An account with this email already exists.'], name=name, email=email, agency_name=agency_name)

    # Create slug from agency name
    slug = re.sub(r'[^a-z0-9]+', '-', agency_name.lower()).strip('-')
    if db.get_agency_by_slug(slug):
        slug = f'{slug}-{os.urandom(2).hex()}'

    # Create agency + owner
    agency_id = invite.get('agency_id')
    if not agency_id:
        agency_id = db.create_agency(agency_name, slug)
        db.seed_agency_defaults(agency_id)

    owner_id = db.create_owner(agency_id, name, email, hash_password(password))
    db.use_invite_code(invite_code, owner_id)

    session['owner_id'] = owner_id
    return redirect(url_for('admin_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    owner = db.get_owner_by_email(email)
    if not owner or owner['password_hash'] != hash_password(password):
        return render_template('auth/login.html', error='Invalid email or password.', email=email)

    session['owner_id'] = owner['id']
    return redirect(url_for('admin_dashboard'))


@app.route('/logout')
def logout():
    session.pop('owner_id', None)
    return redirect(url_for('home'))


# ──────────────────────────────────────
# Inject pending meeting count into all admin templates
# ──────────────────────────────────────

@app.context_processor
def inject_pending_meetings():
    if 'owner_id' in session:
        agency = get_current_agency()
        if agency:
            return {'pending_meetings': db.count_pending_meetings(agency['id'])}
    return {'pending_meetings': 0}


# ──────────────────────────────────────
# Agency Owner Admin routes
# ──────────────────────────────────────

@app.route('/admin')
@login_required
def admin_dashboard():
    agency = get_current_agency()
    owner = get_current_owner()
    onboardings = db.list_onboardings_by_agency(agency['id'])
    return render_template(
        'admin/dashboard.html',
        agency=agency,
        owner=owner,
        onboardings=onboardings,
    )


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    agency = get_current_agency()
    owner = get_current_owner()

    if request.method == 'POST':
        db.update_agency(
            agency['id'],
            name=request.form.get('name', agency['name']),
            slug=request.form.get('slug', agency['slug']),
            primary_color=request.form.get('primary_color', agency['primary_color']),
            secondary_color=request.form.get('secondary_color', agency['secondary_color']),
            logo_url=request.form.get('logo_url', agency['logo_url']),
            airtable_token=request.form.get('airtable_token', agency.get('airtable_token', '')),
            airtable_base_id=request.form.get('airtable_base_id', agency.get('airtable_base_id', '')),
        )
        agency = db.get_agency_by_id(agency['id'])
        return render_template('admin/settings.html', agency=agency, owner=owner, success=True)

    return render_template('admin/settings.html', agency=agency, owner=owner)


@app.route('/admin/meetings')
@login_required
def admin_meetings():
    agency = get_current_agency()
    owner = get_current_owner()
    meetings = db.list_meeting_requests(agency['id'])
    return render_template('admin/meetings.html', agency=agency, owner=owner, meetings=meetings)


@app.route('/admin/meetings/<meeting_id>/status', methods=['POST'])
@login_required
def admin_meeting_status(meeting_id):
    body = request.get_json() or {}
    status = body.get('status', '')
    if status not in ('confirmed', 'declined'):
        return jsonify({'error': 'Invalid status.'}), 400
    db.update_meeting_request_status(meeting_id, status)
    return jsonify({'success': True})


@app.route('/admin/mail', methods=['GET', 'POST'])
@login_required
def admin_mail():
    agency = get_current_agency()
    owner = get_current_owner()
    onboardings = db.list_onboardings_by_agency(agency['id'])

    sent = False
    error = None

    if request.method == 'POST':
        to_email = request.form.get('to', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()

        if not to_email or not subject or not body:
            error = 'All fields are required.'
        elif not notification_service:
            error = 'Email service is not configured. Set SMTP credentials in .env file.'
        else:
            try:
                notification_service.send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                )
                sent = True
            except Exception as e:
                error = f'Failed to send: {e}'

    return render_template(
        'admin/mail.html',
        agency=agency,
        owner=owner,
        onboardings=onboardings,
        sent=sent,
        error=error,
        mail_configured=notification_service is not None,
    )


@app.route('/admin/client/<onboarding_id>')
@login_required
def admin_client_detail(onboarding_id):
    agency = get_current_agency()
    owner = get_current_owner()
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        abort(404)
    return render_template('admin/client_detail.html', agency=agency, owner=owner, record=record)


# ──────────────────────────────────────
# Admin — Onboarding Setup (dynamic forms & templates)
# ──────────────────────────────────────

@app.route('/admin/onboarding-setup')
@login_required
def admin_onboarding_setup():
    agency = get_current_agency()
    owner = get_current_owner()
    sections = db.list_form_sections(agency['id'])
    for section in sections:
        section['questions'] = db.list_form_questions(section['id'])
    templates = db.list_document_templates(agency['id'])
    for t in templates:
        t['linked_sections'] = json.loads(t['section_ids']) if t['section_ids'] else []
    return render_template(
        'admin/onboarding_setup.html',
        agency=agency,
        owner=owner,
        sections=sections,
        templates=templates,
    )


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


@app.route('/admin/api/questions', methods=['POST'])
@login_required
def api_create_question():
    agency = get_current_agency()
    data = request.get_json()
    if not data or not data.get('label', '').strip() or not data.get('section_id'):
        return jsonify({'error': 'Label and section_id are required.'}), 400
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


# ──────────────────────────────────────
# Admin API — Airtable Setup
# ──────────────────────────────────────

@app.route('/admin/api/airtable/setup', methods=['POST'])
@login_required
def api_airtable_setup():
    agency = get_current_agency()
    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404

    token = agency.get('airtable_token', '')
    base_id = agency.get('airtable_base_id', '')
    if not token or not base_id:
        return jsonify({'error': 'Please save your Airtable token and base ID first.'}), 400

    try:
        from services.airtable_service import AirtableService
        svc = AirtableService(token, base_id)
        table_id = svc.create_clients_table()
        db.update_agency(agency['id'], airtable_table_id=table_id)
        return jsonify({'success': True, 'table_id': table_id})
    except Exception as e:
        logger.error(f'Airtable setup error: {e}')
        return jsonify({'error': str(e)}), 500


# ──────────────────────────────────────
# Per-agency public onboarding routes
# ──────────────────────────────────────

@app.route('/a/<slug>')
def agency_onboard_form(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    form_config = db.get_agency_form_config(agency['id'])
    for section in form_config:
        for q in section['questions']:
            if isinstance(q['options'], str):
                try:
                    q['options'] = json.loads(q['options'])
                except Exception:
                    q['options'] = []
    return render_template('index.html', agency=agency, agency_name=agency['name'], form_sections=form_config)


@app.route('/a/<slug>/onboard', methods=['POST'])
def agency_onboard(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'success': False, 'errors': ['Agency not found.']}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'errors': ['No data provided.']}), 400

    form_config = db.get_agency_form_config(agency['id'])
    required_fields = []
    for section in form_config:
        for q in section['questions']:
            if q['is_required']:
                required_fields.append({'field_key': q['field_key'], 'field_type': q['field_type'], 'label': q['label']})
    is_valid, errors = validate_onboarding_data(data, required_fields=required_fields if required_fields else None)
    if not is_valid:
        return jsonify({'success': False, 'errors': errors}), 400

    onboarding_id = f"ONB-{datetime.now():%Y%m%d%H%M%S}"

    store_data = {
        **data,
        'onboarding_id': onboarding_id,
        'agency_id': agency['id'],
        'agency_name': agency['name'],
        'timestamp': datetime.now().isoformat(),
        'status': 'processing',
        'documents': [],
        'clickup_list_id': None,
        'clickup_list_url': '',
        'tasks_created': 0,
        'airtable_record_id': None,
    }

    db.save_onboarding(onboarding_id, agency['id'], store_data)

    # Create client account with auto-generated password
    client_password = os.urandom(4).hex()  # 8-char random password
    db.create_client_account(
        agency_id=agency['id'],
        onboarding_id=onboarding_id,
        client_email=data['email'],
        client_name=data['full_name'],
        password_hash=hash_password(client_password),
    )

    dashboard_url = f'{request.host_url.rstrip("/")}/a/{slug}/dashboard/{onboarding_id}'
    thread = threading.Thread(
        target=process_onboarding,
        args=(onboarding_id, data, agency['name'], dashboard_url),
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'onboarding_id': onboarding_id,
        'client_password': client_password,
        'message': 'Onboarding initiated successfully!',
        'dashboard_url': f'/a/{slug}/dashboard/{onboarding_id}',
    }), 202


@app.route('/a/<slug>/demo', methods=['POST'])
def agency_demo(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'success': False, 'errors': ['Agency not found.']}), 404

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

    onboarding_id = f"ONB-{datetime.now():%Y%m%d%H%M%S}"

    store_data = {
        **sample_data,
        'onboarding_id': onboarding_id,
        'agency_id': agency['id'],
        'agency_name': agency['name'],
        'timestamp': datetime.now().isoformat(),
        'status': 'processing',
        'documents': [],
        'clickup_list_id': None,
        'clickup_list_url': '',
        'tasks_created': 0,
        'airtable_record_id': None,
    }

    db.save_onboarding(onboarding_id, agency['id'], store_data)

    client_password = os.urandom(4).hex()
    db.create_client_account(
        agency_id=agency['id'],
        onboarding_id=onboarding_id,
        client_email=sample_data['email'],
        client_name=sample_data['full_name'],
        password_hash=hash_password(client_password),
    )

    thread = threading.Thread(
        target=process_onboarding,
        args=(onboarding_id, sample_data, agency['name']),
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'onboarding_id': onboarding_id,
        'client_password': client_password,
        'message': 'Demo onboarding initiated!',
        'dashboard_url': f'/a/{slug}/dashboard/{onboarding_id}',
    }), 202


@app.route('/a/<slug>/login', methods=['GET', 'POST'])
def client_login(slug):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404

    if request.method == 'GET':
        return render_template('client_login.html', agency=agency)

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    accounts = db.get_client_account(agency['id'], email)
    matched = None
    for acct in accounts:
        if acct['password_hash'] == hash_password(password):
            matched = acct
            break

    if not matched:
        return render_template('client_login.html', agency=agency, error='Invalid email or password.', email=email)

    session['client_onboarding_id'] = matched['onboarding_id']
    session['client_agency_id'] = agency['id']
    return redirect(f"/a/{slug}/dashboard/{matched['onboarding_id']}")


@app.route('/a/<slug>/logout-client')
def client_logout(slug):
    session.pop('client_onboarding_id', None)
    session.pop('client_agency_id', None)
    return redirect(f'/a/{slug}/login')


def client_login_required(slug, onboarding_id):
    """Check if client is logged in for this dashboard."""
    if session.get('client_onboarding_id') == onboarding_id:
        return True
    # Also allow agency owners to view their clients
    if 'owner_id' in session:
        agency = get_current_agency()
        if agency:
            record = db.get_onboarding(onboarding_id)
            if record and record['agency_id'] == agency['id']:
                return True
    return False


@app.route('/a/<slug>/dashboard/<onboarding_id>')
def client_dashboard(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404

    if not client_login_required(slug, onboarding_id):
        return redirect(f'/a/{slug}/login')

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return render_template('error.html', message='Onboarding ID not found.'), 404

    return render_template(
        'dashboard.html',
        data=record['data'],
        onboarding_id=onboarding_id,
        tab='overview',
        agency=agency,
        agency_name=agency['name'],
        slug=slug,
    )


@app.route('/a/<slug>/dashboard/<onboarding_id>/documents')
def client_dashboard_documents(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    if not client_login_required(slug, onboarding_id):
        return redirect(f'/a/{slug}/login')

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return render_template('error.html', message='Onboarding ID not found.'), 404

    return render_template(
        'dashboard.html',
        data=record['data'],
        onboarding_id=onboarding_id,
        tab='documents',
        agency=agency,
        agency_name=agency['name'],
        slug=slug,
    )


@app.route('/a/<slug>/dashboard/<onboarding_id>/document/<doc_type>')
def client_view_document(slug, onboarding_id, doc_type):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    if not client_login_required(slug, onboarding_id):
        return redirect(f'/a/{slug}/login')

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return render_template('error.html', message='Onboarding ID not found.'), 404

    data = record['data']
    document = None
    for doc in data.get('documents', []):
        if doc['type'] == doc_type:
            document = doc
            doc['read'] = True
            break

    if not document:
        return render_template('error.html', message='Document not found.'), 404

    # Persist read status
    db.update_onboarding(onboarding_id, data=data)

    # Convert markdown content to HTML
    content = document.get('content', '')
    lines = content.split('\n')
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('### '):
            html_lines.append(f'<h3>{html_module.escape(stripped[4:])}</h3>')
        elif stripped.startswith('## '):
            html_lines.append(f'<h2>{html_module.escape(stripped[3:])}</h2>')
        elif stripped.startswith('# '):
            html_lines.append(f'<h1>{html_module.escape(stripped[2:])}</h1>')
        elif stripped.startswith('- ') or stripped.startswith('* '):
            html_lines.append(f'<li>{html_module.escape(stripped[2:])}</li>')
        elif re.match(r'^\d+\.\s', stripped):
            text = re.sub(r'^\d+\.\s', '', stripped)
            html_lines.append(f'<li>{html_module.escape(text)}</li>')
        elif stripped == '---' or stripped == '***':
            html_lines.append('<hr>')
        elif stripped == '':
            html_lines.append('<br>')
        else:
            # Handle bold **text**
            escaped = html_module.escape(stripped)
            escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
            html_lines.append(f'<p>{escaped}</p>')
    content_html = '\n'.join(html_lines)
    document['content_html'] = content_html

    return render_template(
        'document.html',
        data=data,
        document=document,
        onboarding_id=onboarding_id,
        agency=agency,
        agency_name=agency['name'],
        slug=slug,
    )


# ──────────────────────────────────────
# Client dashboard — PDF Download
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/document/<doc_type>/pdf')
def client_download_pdf(slug, onboarding_id, doc_type):
    from utils.pdf_generator import generate_pdf

    agency = db.get_agency_by_slug(slug)
    if not agency:
        abort(404)
    if not client_login_required(slug, onboarding_id):
        abort(403)
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        abort(404)

    document = None
    for doc in record['data'].get('documents', []):
        if doc['type'] == doc_type:
            document = doc
            break

    if not document or not document.get('content'):
        abort(404)

    pdf_bytes = generate_pdf(
        title=document['title'],
        content=document['content'],
        agency_name=agency['name'],
    )

    filename = f"{document['title'].replace(' ', '_')}_{onboarding_id}.pdf"
    import io
    buf = io.BytesIO(pdf_bytes)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


# ──────────────────────────────────────
# Client dashboard — Regenerate Documents
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/regenerate-documents', methods=['POST'])
def regenerate_documents(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    if not ai_generator:
        return jsonify({'error': 'AI service is not available.'}), 503

    data = record['data']

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

    thread = threading.Thread(target=run_regeneration)
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Documents are being generated. Refresh in a minute.'})


# ──────────────────────────────────────
# Client dashboard — Meeting Request
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/request-meeting', methods=['POST'])
def request_meeting(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    body = request.get_json() or {}
    preferred_date = body.get('date', '').strip()
    preferred_time = body.get('time', '').strip()
    topic = body.get('topic', '').strip()
    notes = body.get('notes', '').strip()

    if not preferred_date or not topic:
        return jsonify({'error': 'Date and topic are required.'}), 400

    data = record['data']
    db.create_meeting_request(
        agency_id=agency['id'],
        onboarding_id=onboarding_id,
        client_name=data.get('full_name', ''),
        client_email=data.get('email', ''),
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        topic=topic,
        notes=notes,
    )

    # Send email notification to agency owner
    if notification_service:
        try:
            owners = db.list_owners_by_agency(agency['id'])
            for owner in owners:
                notification_service.send_email(
                    to_email=owner['email'],
                    subject=f"Meeting Request from {data.get('full_name', 'a client')}",
                    body=f"Client: {data.get('full_name')}\nDate: {preferred_date} {preferred_time}\nTopic: {topic}\nNotes: {notes}",
                )
        except Exception as e:
            logger.warning(f'Meeting notification email failed: {e}')

    # Sync meeting info to Airtable
    airtable_svc = get_airtable_for_agency(agency)
    if airtable_svc:
        try:
            airtable_svc.update_meeting_info(onboarding_id, f'{preferred_date} {preferred_time}'.strip(), topic)
        except Exception as e:
            logger.warning(f'Airtable meeting update failed: {e}')

    return jsonify({'success': True, 'message': 'Meeting request sent.'})


# ──────────────────────────────────────
# Client dashboard — AI Chatbot API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/chat', methods=['POST'])
def client_chat(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    body = request.get_json()
    user_message = (body or {}).get('message', '').strip()
    history = (body or {}).get('history', [])
    if not user_message:
        return jsonify({'error': 'Empty message.'}), 400

    data = record['data']
    industry = data.get('department', 'general')
    services = data.get('services', [data.get('role', '')])
    goals = data.get('goals', '')
    challenges = data.get('challenges', '')
    company = data.get('full_name', 'the client')

    system_prompt = (
        f"You are a helpful marketing strategist assistant for {agency['name']}. "
        f"You are speaking with {company}, a client in the {industry} industry. "
        f"Their selected services: {', '.join(s.replace('_', ' ') for s in services)}. "
        f"Their goals: {goals}. Their challenges: {challenges}. "
        f"Provide specific, actionable advice tailored to their industry and situation. "
        f"Keep responses concise (2-4 paragraphs max). Be professional and helpful. "
        f"Do not use markdown headers. Use plain text with short paragraphs."
    )

    if not ai_generator:
        return jsonify({'reply': 'The AI assistant is not currently available. Please contact your account manager for help.'})

    try:
        messages = [{'role': 'system', 'content': system_prompt}]
        for msg in history[-10:]:
            messages.append({'role': msg.get('role', 'user'), 'content': msg.get('content', '')})
        messages.append({'role': 'user', 'content': user_message})

        response = ai_generator.client.chat.completions.create(
            model='gpt-4',
            messages=messages,
            max_tokens=800,
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({'reply': reply})
    except Exception as e:
        logger.error(f'Chat error for {onboarding_id}: {e}')
        return jsonify({'reply': 'Sorry, I encountered an error. Please try again.'}), 500


# ──────────────────────────────────────
# Client dashboard — Tools tab
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/tools')
def client_dashboard_tools(slug, onboarding_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return render_template('error.html', message='Agency not found.'), 404
    if not client_login_required(slug, onboarding_id):
        return redirect(f'/a/{slug}/login')

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return render_template('error.html', message='Onboarding ID not found.'), 404

    tool_counts = db.count_tool_outputs(onboarding_id)

    return render_template(
        'dashboard.html',
        data=record['data'],
        onboarding_id=onboarding_id,
        tab='tools',
        agency=agency,
        agency_name=agency['name'],
        slug=slug,
        tool_counts=tool_counts,
    )


# ──────────────────────────────────────
# Client dashboard — Individual Tool Page
# ──────────────────────────────────────

TOOLS_CONFIG = {
    'content_calendar': {
        'title': 'Content Calendar',
        'desc': 'Plan and schedule your content across all platforms.',
        'icon': 'C', 'color': '#059669', 'bg': '#ecfdf5',
        'system': 'You are a content strategist. Create a detailed, well-structured content calendar. Include specific post topics, platforms, content types, and posting schedule. Format with clear headers and bullet points.',
        'default_prompt': 'Create a detailed content calendar for the next 4 weeks for my brand.',
    },
    'competitor_analysis': {
        'title': 'Competitor Analysis',
        'desc': 'AI-powered breakdown of competitor marketing strategies.',
        'icon': 'A', 'color': '#3b82f6', 'bg': '#eff6ff',
        'system': 'You are a competitive intelligence analyst. Provide a thorough competitor analysis including market positioning, strengths/weaknesses, marketing channels used, content strategy, and recommendations. Format with clear headers and sections.',
        'default_prompt': 'Provide a competitor analysis for companies in my industry.',
    },
    'campaign_ideas': {
        'title': 'Campaign Ideas',
        'desc': 'Tailored campaign concepts for your goals and audience.',
        'icon': 'I', 'color': '#d97706', 'bg': '#fef3c7',
        'system': 'You are a creative marketing director. Generate detailed, actionable campaign ideas. Each idea should include a concept name, target audience, channels, key messaging, timeline, and success metrics. Format clearly.',
        'default_prompt': 'Generate 3 detailed marketing campaign ideas for my brand.',
    },
    'audience_personas': {
        'title': 'Audience Personas',
        'desc': 'Build detailed buyer personas to sharpen your messaging.',
        'icon': 'P', 'color': '#db2777', 'bg': '#fce7f3',
        'system': 'You are a market research specialist. Create detailed buyer personas including demographics, psychographics, pain points, goals, preferred channels, buying behavior, and messaging angles. Format each persona clearly.',
        'default_prompt': 'Create 3 detailed buyer personas for my target audience.',
    },
    'social_copy': {
        'title': 'Social Copy Generator',
        'desc': 'Generate on-brand social media captions and copy.',
        'icon': 'S', 'color': '#7c3aed', 'bg': '#f3e8ff',
        'system': 'You are a social media copywriter. Write engaging, on-brand social media copy. Include platform-specific versions (Instagram, LinkedIn, Twitter/X, Facebook), relevant hashtags, and call-to-actions. Format clearly by platform.',
        'default_prompt': 'Write social media posts for my brand across all major platforms.',
    },
    'seo_keywords': {
        'title': 'SEO Keyword Research',
        'desc': 'Discover keyword opportunities for your content strategy.',
        'icon': 'K', 'color': '#16a34a', 'bg': '#f0fdf4',
        'system': 'You are an SEO specialist. Provide keyword research with primary keywords, long-tail variations, search intent, difficulty estimates, and content recommendations for each keyword cluster. Format as organized tables or lists.',
        'default_prompt': 'Research SEO keywords and topics for my industry and services.',
    },
}


@app.route('/a/<slug>/dashboard/<onboarding_id>/tool/<tool_type>')
def client_tool_page(slug, onboarding_id, tool_type):
    if tool_type not in TOOLS_CONFIG:
        abort(404)

    agency = db.get_agency_by_slug(slug)
    if not agency:
        abort(404)
    if not client_login_required(slug, onboarding_id):
        return redirect(f'/a/{slug}/login')

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        abort(404)

    # Content Calendar gets its own template
    if tool_type == 'content_calendar':
        import calendar as cal_mod
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        posts = db.list_calendar_posts(onboarding_id, year, month)
        return render_template(
            'content_calendar.html',
            agency=agency,
            agency_name=agency['name'],
            slug=slug,
            onboarding_id=onboarding_id,
            posts=posts,
            year=year,
            month=month,
            data=record['data'],
        )

    ctx = dict(agency=agency, agency_name=agency['name'], slug=slug, onboarding_id=onboarding_id, data=record['data'])

    if tool_type == 'competitor_analysis':
        ctx['competitors'] = db.list_competitors(onboarding_id)
        return render_template('tool_competitors.html', **ctx)

    if tool_type == 'campaign_ideas':
        ctx['campaigns'] = db.list_campaigns(onboarding_id)
        return render_template('tool_campaigns.html', **ctx)

    if tool_type == 'audience_personas':
        ctx['personas'] = db.list_personas(onboarding_id)
        return render_template('tool_personas.html', **ctx)

    if tool_type == 'social_copy':
        ctx['copies'] = db.list_copies(onboarding_id)
        return render_template('tool_social_copy.html', **ctx)

    if tool_type == 'seo_keywords':
        ctx['keywords'] = db.list_seo_keywords(onboarding_id)
        return render_template('tool_seo.html', **ctx)

    tool = TOOLS_CONFIG[tool_type]
    outputs = db.list_tool_outputs(onboarding_id, tool_type)

    return render_template(
        'tool_page.html',
        agency=agency,
        agency_name=agency['name'],
        slug=slug,
        onboarding_id=onboarding_id,
        tool_type=tool_type,
        tool=tool,
        outputs=outputs,
        data=record['data'],
    )


@app.route('/a/<slug>/dashboard/<onboarding_id>/tool/<tool_type>/generate', methods=['POST'])
def client_tool_generate(slug, onboarding_id, tool_type):
    if tool_type not in TOOLS_CONFIG:
        return jsonify({'error': 'Unknown tool.'}), 404

    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Agency not found.'}), 404
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401

    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    body = request.get_json() or {}
    user_prompt = body.get('prompt', '').strip()
    tool = TOOLS_CONFIG[tool_type]

    if not user_prompt:
        user_prompt = tool['default_prompt']

    if not ai_generator:
        return jsonify({'error': 'AI assistant is not available.'}), 503

    data = record['data']
    industry = data.get('department', 'general')
    services = data.get('services', [data.get('role', '')])
    goals = data.get('goals', '')
    company = data.get('full_name', 'the client')

    context = (
        f"Client: {company}. Industry: {industry}. "
        f"Services: {', '.join(s.replace('_', ' ') for s in services)}. "
        f"Goals: {goals}."
    )

    try:
        response = ai_generator.client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': f"{tool['system']}\n\nClient context: {context}"},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=2000,
        )
        output = response.choices[0].message.content.strip()

        # Save to database
        output_id = db.save_tool_output(
            onboarding_id=onboarding_id,
            agency_id=agency['id'],
            tool_type=tool_type,
            title=user_prompt[:100],
            prompt=user_prompt,
            output=output,
        )

        return jsonify({'success': True, 'id': output_id, 'output': output, 'created_at': datetime.now().isoformat()})
    except Exception as e:
        logger.error(f'Tool generate error ({tool_type}): {e}')
        return jsonify({'error': 'Failed to generate. Please try again.'}), 500


@app.route('/a/<slug>/dashboard/<onboarding_id>/tool/<tool_type>/<output_id>/delete', methods=['POST'])
def client_tool_delete(slug, onboarding_id, tool_type, output_id):
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401

    output = db.get_tool_output(output_id)
    if not output or output['onboarding_id'] != onboarding_id:
        return jsonify({'error': 'Not found.'}), 404

    db.delete_tool_output(output_id)
    return jsonify({'success': True})


@app.route('/a/<slug>/dashboard/<onboarding_id>/tool/<tool_type>/<output_id>/pdf')
def client_tool_pdf(slug, onboarding_id, tool_type, output_id):
    from utils.pdf_generator import generate_pdf

    agency = db.get_agency_by_slug(slug)
    if not agency:
        abort(404)
    if not client_login_required(slug, onboarding_id):
        abort(403)

    output = db.get_tool_output(output_id)
    if not output or output['onboarding_id'] != onboarding_id:
        abort(404)

    tool = TOOLS_CONFIG.get(tool_type, {})
    pdf_bytes = generate_pdf(
        title=tool.get('title', 'Tool Output'),
        content=output['output'],
        agency_name=agency['name'],
    )

    import io
    filename = f"{tool.get('title', 'output').replace(' ', '_')}_{output_id[:8]}.pdf"
    buf = io.BytesIO(pdf_bytes)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


# ──────────────────────────────────────
# Competitors API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/competitors', methods=['GET'])
def api_list_competitors(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'items': db.list_competitors(onboarding_id)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/competitors', methods=['POST'])
def api_create_competitor(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency: return jsonify({'error':'Not found.'}),404
    body = request.get_json() or {}
    cid = db.create_competitor(onboarding_id, agency['id'], **body)
    return jsonify({'success':True, 'item': db.get_competitor(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/competitors/<cid>', methods=['PUT'])
def api_update_competitor(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    body = request.get_json() or {}
    db.update_competitor(cid, **body)
    return jsonify({'success':True, 'item': db.get_competitor(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/competitors/<cid>', methods=['DELETE'])
def api_delete_competitor(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.delete_competitor(cid)
    return jsonify({'success':True})

@app.route('/a/<slug>/dashboard/<onboarding_id>/competitors/ai-generate', methods=['POST'])
def api_ai_competitors(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    record = db.get_onboarding(onboarding_id)
    if not agency or not record: return jsonify({'error':'Not found.'}),404
    if not ai_generator: return jsonify({'error':'AI not available.'}),503
    data = record['data']
    import json as json_mod
    try:
        resp = ai_generator.client.chat.completions.create(model='gpt-4', messages=[
            {'role':'system','content':'You are a competitive analyst. Return only valid JSON arrays. No markdown.'},
            {'role':'user','content':f"Identify 4 competitors for {data.get('full_name','')} in the {data.get('department','general')} industry. Services: {data.get('role','')}. Return JSON: [{{'name':'','website':'','strengths':'','weaknesses':'','channels':'','positioning':'','threat_level':'high/medium/low'}}]"}
        ], max_tokens=1500)
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0].strip()
        items = json_mod.loads(raw)
        created = []
        for it in items:
            cid = db.create_competitor(onboarding_id, agency['id'], **it)
            created.append(db.get_competitor(cid))
        return jsonify({'success':True, 'items':created})
    except Exception as e:
        logger.error(f'AI competitors error: {e}')
        return jsonify({'error':'Failed to generate.'}),500


# ──────────────────────────────────────
# Campaigns API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/campaigns', methods=['GET'])
def api_list_campaigns(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'items': db.list_campaigns(onboarding_id)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/campaigns', methods=['POST'])
def api_create_campaign(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency: return jsonify({'error':'Not found.'}),404
    body = request.get_json() or {}
    cid = db.create_campaign(onboarding_id, agency['id'], **body)
    return jsonify({'success':True, 'item': db.get_campaign(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/campaigns/<cid>', methods=['PUT'])
def api_update_campaign(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    body = request.get_json() or {}
    db.update_campaign(cid, **body)
    return jsonify({'success':True, 'item': db.get_campaign(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/campaigns/<cid>', methods=['DELETE'])
def api_delete_campaign(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.delete_campaign(cid)
    return jsonify({'success':True})

@app.route('/a/<slug>/dashboard/<onboarding_id>/campaigns/ai-generate', methods=['POST'])
def api_ai_campaigns(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    record = db.get_onboarding(onboarding_id)
    if not agency or not record: return jsonify({'error':'Not found.'}),404
    if not ai_generator: return jsonify({'error':'AI not available.'}),503
    data = record['data']
    import json as json_mod
    try:
        resp = ai_generator.client.chat.completions.create(model='gpt-4', messages=[
            {'role':'system','content':'You are a marketing strategist. Return only valid JSON arrays. No markdown.'},
            {'role':'user','content':f"Create 3 marketing campaign ideas for {data.get('full_name','')} in {data.get('department','general')} industry. Goals: {data.get('goals','')}. Return JSON: [{{'name':'','objective':'','target_audience':'','channels':'','budget':'','kpis':'','description':'','stage':'idea'}}]"}
        ], max_tokens=1500)
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0].strip()
        items = json_mod.loads(raw)
        created = []
        for it in items:
            cid = db.create_campaign(onboarding_id, agency['id'], **it)
            created.append(db.get_campaign(cid))
        return jsonify({'success':True, 'items':created})
    except Exception as e:
        logger.error(f'AI campaigns error: {e}')
        return jsonify({'error':'Failed to generate.'}),500


# ──────────────────────────────────────
# Personas API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/personas', methods=['GET'])
def api_list_personas(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'items': db.list_personas(onboarding_id)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/personas', methods=['POST'])
def api_create_persona(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency: return jsonify({'error':'Not found.'}),404
    body = request.get_json() or {}
    pid = db.create_persona(onboarding_id, agency['id'], **body)
    return jsonify({'success':True, 'item': db.get_persona(pid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/personas/<pid>', methods=['PUT'])
def api_update_persona(slug, onboarding_id, pid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    body = request.get_json() or {}
    db.update_persona(pid, **body)
    return jsonify({'success':True, 'item': db.get_persona(pid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/personas/<pid>', methods=['DELETE'])
def api_delete_persona(slug, onboarding_id, pid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.delete_persona(pid)
    return jsonify({'success':True})

@app.route('/a/<slug>/dashboard/<onboarding_id>/personas/ai-generate', methods=['POST'])
def api_ai_personas(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    record = db.get_onboarding(onboarding_id)
    if not agency or not record: return jsonify({'error':'Not found.'}),404
    if not ai_generator: return jsonify({'error':'AI not available.'}),503
    data = record['data']
    import json as json_mod
    COLORS = ['#E1306C','#0077B5','#7c3aed','#d97706','#059669','#dc2626']
    try:
        resp = ai_generator.client.chat.completions.create(model='gpt-4', messages=[
            {'role':'system','content':'You are a market research expert. Return only valid JSON arrays. No markdown.'},
            {'role':'user','content':f"Create 3 buyer personas for {data.get('full_name','')} in {data.get('department','general')} industry. Goals: {data.get('goals','')}. Return JSON: [{{'name':'Persona Name','age_range':'25-34','job_title':'','location':'','income':'','bio':'2-3 sentences','goals':'','pain_points':'','channels':'','brands':'Brands they follow','buying_behavior':'','messaging_angle':''}}]"}
        ], max_tokens=2000)
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0].strip()
        items = json_mod.loads(raw)
        created = []
        for i, it in enumerate(items):
            it['color'] = COLORS[i % len(COLORS)]
            pid = db.create_persona(onboarding_id, agency['id'], **it)
            created.append(db.get_persona(pid))
        return jsonify({'success':True, 'items':created})
    except Exception as e:
        logger.error(f'AI personas error: {e}')
        return jsonify({'error':'Failed to generate.'}),500


# ──────────────────────────────────────
# Social Copy API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/copies', methods=['GET'])
def api_list_copies(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'items': db.list_copies(onboarding_id)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/copies', methods=['POST'])
def api_create_copy(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency: return jsonify({'error':'Not found.'}),404
    body = request.get_json() or {}
    cid = db.create_copy(onboarding_id, agency['id'], **body)
    return jsonify({'success':True, 'item': db.get_copy(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/copies/<cid>/favorite', methods=['POST'])
def api_toggle_copy_fav(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.toggle_copy_favorite(cid)
    return jsonify({'success':True, 'item': db.get_copy(cid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/copies/<cid>', methods=['DELETE'])
def api_delete_copy(slug, onboarding_id, cid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.delete_copy(cid)
    return jsonify({'success':True})

@app.route('/a/<slug>/dashboard/<onboarding_id>/copies/ai-generate', methods=['POST'])
def api_ai_copies(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    record = db.get_onboarding(onboarding_id)
    if not agency or not record: return jsonify({'error':'Not found.'}),404
    if not ai_generator: return jsonify({'error':'AI not available.'}),503
    data = record['data']
    body = request.get_json() or {}
    topic = body.get('topic', 'general brand post')
    import json as json_mod
    try:
        resp = ai_generator.client.chat.completions.create(model='gpt-4', messages=[
            {'role':'system','content':'You are a social media copywriter. Return only valid JSON arrays. No markdown.'},
            {'role':'user','content':f"Write social media copy about '{topic}' for {data.get('full_name','')} in {data.get('department','general')} industry. Create one post per platform. Return JSON: [{{'platform':'Instagram','content_type':'Post','topic':'{topic}','copy_text':'The caption text','hashtags':'#tag1 #tag2'}},{{'platform':'LinkedIn','content_type':'Article','topic':'{topic}','copy_text':'...','hashtags':''}},{{'platform':'Twitter','content_type':'Post','topic':'{topic}','copy_text':'...','hashtags':''}},{{'platform':'Facebook','content_type':'Post','topic':'{topic}','copy_text':'...','hashtags':''}}]"}
        ], max_tokens=2000)
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0].strip()
        items = json_mod.loads(raw)
        created = []
        for it in items:
            cid = db.create_copy(onboarding_id, agency['id'], **it)
            created.append(db.get_copy(cid))
        return jsonify({'success':True, 'items':created})
    except Exception as e:
        logger.error(f'AI copy error: {e}')
        return jsonify({'error':'Failed to generate.'}),500


# ──────────────────────────────────────
# SEO Keywords API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/keywords', methods=['GET'])
def api_list_keywords(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'items': db.list_seo_keywords(onboarding_id)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/keywords', methods=['POST'])
def api_create_keyword(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency: return jsonify({'error':'Not found.'}),404
    body = request.get_json() or {}
    kid = db.create_seo_keyword(onboarding_id, agency['id'], **body)
    return jsonify({'success':True, 'item': db.get_seo_keyword(kid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/keywords/<kid>', methods=['PUT'])
def api_update_keyword(slug, onboarding_id, kid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    body = request.get_json() or {}
    db.update_seo_keyword(kid, **body)
    return jsonify({'success':True, 'item': db.get_seo_keyword(kid)})

@app.route('/a/<slug>/dashboard/<onboarding_id>/keywords/<kid>', methods=['DELETE'])
def api_delete_keyword(slug, onboarding_id, kid):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    db.delete_seo_keyword(kid)
    return jsonify({'success':True})

@app.route('/a/<slug>/dashboard/<onboarding_id>/keywords/ai-generate', methods=['POST'])
def api_ai_keywords(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    record = db.get_onboarding(onboarding_id)
    if not agency or not record: return jsonify({'error':'Not found.'}),404
    if not ai_generator: return jsonify({'error':'AI not available.'}),503
    data = record['data']
    import json as json_mod
    try:
        resp = ai_generator.client.chat.completions.create(model='gpt-4', messages=[
            {'role':'system','content':'You are an SEO specialist. Return only valid JSON arrays. No markdown.'},
            {'role':'user','content':f"Research 10 SEO keywords for {data.get('full_name','')} in {data.get('department','general')} industry. Services: {data.get('role','')}. Goals: {data.get('goals','')}. Return JSON: [{{'keyword':'','cluster':'cluster name','search_volume':'1K-10K','difficulty':'low/medium/high','intent':'informational/commercial/transactional/navigational','priority':'high/medium/low','notes':''}}]"}
        ], max_tokens=2000)
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'): raw = raw.split('\n',1)[1].rsplit('```',1)[0].strip()
        items = json_mod.loads(raw)
        created = []
        for it in items:
            kid = db.create_seo_keyword(onboarding_id, agency['id'], **it)
            created.append(db.get_seo_keyword(kid))
        return jsonify({'success':True, 'items':created})
    except Exception as e:
        logger.error(f'AI keywords error: {e}')
        return jsonify({'error':'Failed to generate.'}),500


# ──────────────────────────────────────
# Content Calendar API
# ──────────────────────────────────────

@app.route('/a/<slug>/dashboard/<onboarding_id>/calendar/posts', methods=['GET'])
def calendar_get_posts(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    year = request.args.get('year', type=int, default=datetime.now().year)
    month = request.args.get('month', type=int, default=datetime.now().month)
    posts = db.list_calendar_posts(onboarding_id, year, month)
    return jsonify({'posts': posts})


@app.route('/a/<slug>/dashboard/<onboarding_id>/calendar/posts', methods=['POST'])
def calendar_create_post(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    body = request.get_json() or {}
    post_date = body.get('post_date', '').strip()
    platform = body.get('platform', '').strip()
    if not post_date or not platform:
        return jsonify({'error': 'Date and platform are required.'}), 400

    post_id = db.create_calendar_post(
        onboarding_id=onboarding_id,
        agency_id=agency['id'],
        post_date=post_date,
        post_time=body.get('post_time', ''),
        platform=platform,
        content_type=body.get('content_type', ''),
        title=body.get('title', ''),
        idea=body.get('idea', ''),
        description=body.get('description', ''),
        caption=body.get('caption', ''),
        hashtags=body.get('hashtags', ''),
        media_notes=body.get('media_notes', ''),
        status=body.get('status', 'draft'),
        color=body.get('color', '#667eea'),
    )
    post = db.get_calendar_post(post_id)
    return jsonify({'success': True, 'post': post})


@app.route('/a/<slug>/dashboard/<onboarding_id>/calendar/posts/<post_id>', methods=['PUT'])
def calendar_update_post(slug, onboarding_id, post_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    post = db.get_calendar_post(post_id)
    if not post or post['onboarding_id'] != onboarding_id:
        return jsonify({'error': 'Not found.'}), 404

    body = request.get_json() or {}
    db.update_calendar_post(post_id, **body)
    updated = db.get_calendar_post(post_id)
    return jsonify({'success': True, 'post': updated})


@app.route('/a/<slug>/dashboard/<onboarding_id>/calendar/posts/<post_id>', methods=['DELETE'])
def calendar_delete_post(slug, onboarding_id, post_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    post = db.get_calendar_post(post_id)
    if not post or post['onboarding_id'] != onboarding_id:
        return jsonify({'error': 'Not found.'}), 404
    db.delete_calendar_post(post_id)
    return jsonify({'success': True})


@app.route('/a/<slug>/dashboard/<onboarding_id>/calendar/ai-generate', methods=['POST'])
def calendar_ai_generate(slug, onboarding_id):
    if not client_login_required(slug, onboarding_id):
        return jsonify({'error': 'Unauthorized.'}), 401
    agency = db.get_agency_by_slug(slug)
    if not agency:
        return jsonify({'error': 'Not found.'}), 404
    record = db.get_onboarding(onboarding_id)
    if not record or record['agency_id'] != agency['id']:
        return jsonify({'error': 'Not found.'}), 404

    if not ai_generator:
        return jsonify({'error': 'AI not available.'}), 503

    body = request.get_json() or {}
    week_start = body.get('week_start', '')
    data = record['data']
    industry = data.get('department', 'general')
    services = data.get('services', [data.get('role', '')])
    goals = data.get('goals', '')
    company = data.get('full_name', 'the client')

    prompt = (
        f"Create a 7-day social media content plan starting from {week_start} for {company} "
        f"in the {industry} industry. Services: {', '.join(s.replace('_', ' ') for s in services)}. Goals: {goals}.\n\n"
        f"Return ONLY valid JSON — no markdown, no code fences. Format:\n"
        f'[{{"date":"YYYY-MM-DD","time":"10:00 AM","platform":"Instagram","content_type":"Reel","title":"Short title","idea":"The core idea","description":"Detailed description of the post","caption":"Ready-to-post caption text","hashtags":"#tag1 #tag2","color":"#hex"}}]\n'
        f"Use these platform colors: Instagram=#E1306C, LinkedIn=#0077B5, Twitter=#1DA1F2, Facebook=#4267B2, TikTok=#000000, YouTube=#FF0000. "
        f"Include 2-3 posts per day across different platforms. Make titles catchy, ideas clear, descriptions detailed."
    )

    try:
        response = ai_generator.client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': 'You are a social media strategist. Return only valid JSON arrays. No markdown.'},
                {'role': 'user', 'content': prompt},
            ],
            max_tokens=2000,
        )
        import json
        raw = response.choices[0].message.content.strip()
        # Strip code fences if present
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        posts_data = json.loads(raw)

        created = []
        for p in posts_data:
            post_id = db.create_calendar_post(
                onboarding_id=onboarding_id,
                agency_id=agency['id'],
                post_date=p.get('date', week_start),
                post_time=p.get('time', ''),
                platform=p.get('platform', 'Instagram'),
                content_type=p.get('content_type', ''),
                title=p.get('title', ''),
                idea=p.get('idea', ''),
                description=p.get('description', ''),
                caption=p.get('caption', ''),
                hashtags=p.get('hashtags', ''),
                status='draft',
                color=p.get('color', '#667eea'),
            )
            created.append(db.get_calendar_post(post_id))
        return jsonify({'success': True, 'posts': created, 'count': len(created)})
    except Exception as e:
        logger.error(f'Calendar AI generate error: {e}')
        return jsonify({'error': 'Failed to generate content plan.'}), 500


# ──────────────────────────────────────
# Health checks
# ──────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/health/detailed')
def health_detailed():
    return jsonify({
        'app': 'ok',
        'ai_generator': 'ok' if ai_generator else 'unavailable',
        'notifications': 'ok' if notification_service else 'unavailable',
        'clickup': 'ok' if clickup_service else 'unavailable',
        'airtable': 'per-agency (configured in admin settings)',
    })


# ──────────────────────────────────────
# CLI: Generate invite codes
# ──────────────────────────────────────

@app.cli.command('create-invite')
def create_invite_cli():
    """Generate a new invite code for agency owner registration."""
    code = db.create_invite_code()
    print(f'Invite code created: {code}')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
