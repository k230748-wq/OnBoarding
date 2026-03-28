import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

from utils.logger import setup_logger

logger = setup_logger()

DB_PATH = os.path.join(os.path.dirname(__file__), 'onboarding.db')


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS agencies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                primary_color TEXT DEFAULT '#667eea',
                secondary_color TEXT DEFAULT '#764ba2',
                logo_url TEXT DEFAULT '',
                airtable_token TEXT DEFAULT '',
                airtable_base_id TEXT DEFAULT '',
                airtable_table_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agency_owners (
                id TEXT PRIMARY KEY,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                agency_id TEXT REFERENCES agencies(id),
                created_by TEXT,
                used_by TEXT,
                used_at TEXT,
                created_at TEXT NOT NULL,
                is_used INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS client_accounts (
                id TEXT PRIMARY KEY,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                onboarding_id TEXT UNIQUE NOT NULL,
                client_email TEXT NOT NULL,
                client_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meeting_requests (
                id TEXT PRIMARY KEY,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                onboarding_id TEXT NOT NULL,
                client_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                preferred_date TEXT,
                preferred_time TEXT,
                topic TEXT,
                notes TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calendar_posts (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                post_date TEXT NOT NULL,
                post_time TEXT DEFAULT '',
                platform TEXT NOT NULL,
                content_type TEXT DEFAULT '',
                title TEXT DEFAULT '',
                idea TEXT DEFAULT '',
                description TEXT DEFAULT '',
                caption TEXT DEFAULT '',
                hashtags TEXT DEFAULT '',
                media_notes TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                color TEXT DEFAULT '#667eea',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS competitors (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                name TEXT NOT NULL,
                website TEXT DEFAULT '',
                strengths TEXT DEFAULT '',
                weaknesses TEXT DEFAULT '',
                channels TEXT DEFAULT '',
                positioning TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                threat_level TEXT DEFAULT 'medium',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                name TEXT NOT NULL,
                objective TEXT DEFAULT '',
                target_audience TEXT DEFAULT '',
                channels TEXT DEFAULT '',
                budget TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                kpis TEXT DEFAULT '',
                description TEXT DEFAULT '',
                stage TEXT DEFAULT 'idea',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS personas (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                name TEXT NOT NULL,
                age_range TEXT DEFAULT '',
                job_title TEXT DEFAULT '',
                location TEXT DEFAULT '',
                income TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                goals TEXT DEFAULT '',
                pain_points TEXT DEFAULT '',
                channels TEXT DEFAULT '',
                brands TEXT DEFAULT '',
                buying_behavior TEXT DEFAULT '',
                messaging_angle TEXT DEFAULT '',
                color TEXT DEFAULT '#667eea',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS copy_library (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                platform TEXT NOT NULL,
                content_type TEXT DEFAULT '',
                topic TEXT DEFAULT '',
                copy_text TEXT NOT NULL,
                hashtags TEXT DEFAULT '',
                is_favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seo_keywords (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                keyword TEXT NOT NULL,
                cluster TEXT DEFAULT '',
                search_volume TEXT DEFAULT '',
                difficulty TEXT DEFAULT '',
                intent TEXT DEFAULT '',
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'research',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_outputs (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                tool_type TEXT NOT NULL,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                output TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS onboardings (
                id TEXT PRIMARY KEY,
                onboarding_id TEXT UNIQUE NOT NULL,
                agency_id TEXT NOT NULL REFERENCES agencies(id),
                data TEXT NOT NULL,
                status TEXT DEFAULT 'processing',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

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
        ''')
    logger.info('Database initialized.')


# ---- Agency ----

def create_agency(name, slug, primary_color='#667eea', secondary_color='#764ba2', logo_url=''):
    agency_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO agencies (id, name, slug, primary_color, secondary_color, logo_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (agency_id, name, slug, primary_color, secondary_color, logo_url, datetime.now().isoformat()),
        )
    return agency_id


def get_agency_by_slug(slug):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM agencies WHERE slug = ?', (slug,)).fetchone()
        return dict(row) if row else None


def get_agency_by_id(agency_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM agencies WHERE id = ?', (agency_id,)).fetchone()
        return dict(row) if row else None


def update_agency(agency_id, **kwargs):
    allowed = {'name', 'slug', 'primary_color', 'secondary_color', 'logo_url',
               'airtable_token', 'airtable_base_id', 'airtable_table_id'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [agency_id]
    with get_db() as conn:
        conn.execute(f'UPDATE agencies SET {set_clause} WHERE id = ?', values)


# ---- Agency Owner ----

def create_owner(agency_id, name, email, password_hash):
    owner_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO agency_owners (id, agency_id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (owner_id, agency_id, name, email, password_hash, datetime.now().isoformat()),
        )
    return owner_id


def get_owner_by_email(email):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM agency_owners WHERE email = ?', (email,)).fetchone()
        return dict(row) if row else None


def list_owners_by_agency(agency_id):
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM agency_owners WHERE agency_id = ?', (agency_id,)).fetchall()
        return [dict(r) for r in rows]


def get_owner_by_id(owner_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM agency_owners WHERE id = ?', (owner_id,)).fetchone()
        return dict(row) if row else None


# ---- Invite Codes ----

def create_invite_code(agency_id=None, created_by='system'):
    code = uuid.uuid4().hex[:8].upper()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO invite_codes (code, agency_id, created_by, created_at) VALUES (?, ?, ?, ?)',
            (code, agency_id, created_by, datetime.now().isoformat()),
        )
    return code


def record_invite_usage(code, used_by):
    with get_db() as conn:
        conn.execute(
            'UPDATE invite_codes SET used_by = ?, used_at = ? WHERE code = ?',
            (used_by, datetime.now().isoformat(), code),
        )


def get_invite_code(code):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM invite_codes WHERE code = ?', (code,)).fetchone()
        return dict(row) if row else None


# ---- Onboardings ----

def save_onboarding(onboarding_id, agency_id, data):
    record_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO onboardings (id, onboarding_id, agency_id, data, status, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (record_id, onboarding_id, agency_id, json.dumps(data), 'processing', datetime.now().isoformat()),
        )
    return record_id


def get_onboarding(onboarding_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM onboardings WHERE onboarding_id = ?', (onboarding_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result['data'] = json.loads(result['data'])
        return result


def update_onboarding(onboarding_id, data=None, status=None):
    with get_db() as conn:
        if data is not None:
            conn.execute('UPDATE onboardings SET data = ? WHERE onboarding_id = ?', (json.dumps(data), onboarding_id))
        if status is not None:
            completed = datetime.now().isoformat() if status == 'completed' else None
            conn.execute('UPDATE onboardings SET status = ?, completed_at = ? WHERE onboarding_id = ?', (status, completed, onboarding_id))


# ---- Client Accounts ----

def create_client_account(agency_id, onboarding_id, client_email, client_name, password_hash):
    account_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO client_accounts (id, agency_id, onboarding_id, client_email, client_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (account_id, agency_id, onboarding_id, client_email, client_name, password_hash, datetime.now().isoformat()),
        )
    return account_id


def get_client_account(agency_id, client_email):
    """Return all matching client accounts for login password checking."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM client_accounts WHERE agency_id = ? AND client_email = ?',
            (agency_id, client_email),
        ).fetchall()
        return [dict(r) for r in rows]


def get_client_account_by_onboarding(onboarding_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM client_accounts WHERE onboarding_id = ?', (onboarding_id,)).fetchone()
        return dict(row) if row else None


# ---- Meeting Requests ----

def create_meeting_request(agency_id, onboarding_id, client_name, client_email, preferred_date, preferred_time, topic, notes=''):
    req_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO meeting_requests (id, agency_id, onboarding_id, client_name, client_email, preferred_date, preferred_time, topic, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (req_id, agency_id, onboarding_id, client_name, client_email, preferred_date, preferred_time, topic, notes, datetime.now().isoformat()),
        )
    return req_id


def list_meeting_requests(agency_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM meeting_requests WHERE agency_id = ? ORDER BY created_at DESC', (agency_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def count_pending_meetings(agency_id):
    with get_db() as conn:
        row = conn.execute('SELECT COUNT(*) as c FROM meeting_requests WHERE agency_id = ? AND status = ?', (agency_id, 'pending')).fetchone()
        return row['c'] if row else 0


def update_meeting_request_status(req_id, status):
    with get_db() as conn:
        conn.execute('UPDATE meeting_requests SET status = ? WHERE id = ?', (status, req_id))


def create_calendar_post(onboarding_id, agency_id, post_date, platform, content_type='', title='', idea='', description='', caption='', hashtags='', media_notes='', status='draft', color='#667eea', post_time=''):
    post_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO calendar_posts (id, onboarding_id, agency_id, post_date, post_time, platform, content_type, title, idea, description, caption, hashtags, media_notes, status, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (post_id, onboarding_id, agency_id, post_date, post_time, platform, content_type, title, idea, description, caption, hashtags, media_notes, status, color, now, now),
        )
    return post_id


def update_calendar_post(post_id, **kwargs):
    allowed = {'post_date', 'post_time', 'platform', 'content_type', 'title', 'idea', 'description', 'caption', 'hashtags', 'media_notes', 'status', 'color'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [post_id]
    with get_db() as conn:
        conn.execute(f'UPDATE calendar_posts SET {set_clause} WHERE id = ?', values)


def delete_calendar_post(post_id):
    with get_db() as conn:
        conn.execute('DELETE FROM calendar_posts WHERE id = ?', (post_id,))


def list_calendar_posts(onboarding_id, year=None, month=None):
    with get_db() as conn:
        if year and month:
            start = f'{year}-{month:02d}-01'
            if month == 12:
                end = f'{year+1}-01-01'
            else:
                end = f'{year}-{month+1:02d}-01'
            rows = conn.execute(
                'SELECT * FROM calendar_posts WHERE onboarding_id = ? AND post_date >= ? AND post_date < ? ORDER BY post_date',
                (onboarding_id, start, end),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM calendar_posts WHERE onboarding_id = ? ORDER BY post_date', (onboarding_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_calendar_post(post_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM calendar_posts WHERE id = ?', (post_id,)).fetchone()
        return dict(row) if row else None


# ---- Competitors ----

def create_competitor(onboarding_id, agency_id, **kwargs):
    cid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO competitors (id, onboarding_id, agency_id, name, website, strengths, weaknesses, channels, positioning, notes, threat_level, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (cid, onboarding_id, agency_id, kwargs.get('name',''), kwargs.get('website',''), kwargs.get('strengths',''), kwargs.get('weaknesses',''), kwargs.get('channels',''), kwargs.get('positioning',''), kwargs.get('notes',''), kwargs.get('threat_level','medium'), now, now),
        )
    return cid

def update_competitor(cid, **kwargs):
    allowed = {'name','website','strengths','weaknesses','channels','positioning','notes','threat_level'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    fields['updated_at'] = datetime.now().isoformat()
    s = ', '.join(f'{k} = ?' for k in fields)
    with get_db() as conn: conn.execute(f'UPDATE competitors SET {s} WHERE id = ?', list(fields.values()) + [cid])

def delete_competitor(cid):
    with get_db() as conn: conn.execute('DELETE FROM competitors WHERE id = ?', (cid,))

def list_competitors(onboarding_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM competitors WHERE onboarding_id = ? ORDER BY created_at', (onboarding_id,)).fetchall()]

def get_competitor(cid):
    with get_db() as conn:
        r = conn.execute('SELECT * FROM competitors WHERE id = ?', (cid,)).fetchone()
        return dict(r) if r else None


# ---- Campaigns ----

def create_campaign(onboarding_id, agency_id, **kwargs):
    cid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO campaigns (id, onboarding_id, agency_id, name, objective, target_audience, channels, budget, start_date, end_date, kpis, description, stage, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (cid, onboarding_id, agency_id, kwargs.get('name',''), kwargs.get('objective',''), kwargs.get('target_audience',''), kwargs.get('channels',''), kwargs.get('budget',''), kwargs.get('start_date',''), kwargs.get('end_date',''), kwargs.get('kpis',''), kwargs.get('description',''), kwargs.get('stage','idea'), now, now),
        )
    return cid

def update_campaign(cid, **kwargs):
    allowed = {'name','objective','target_audience','channels','budget','start_date','end_date','kpis','description','stage'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    fields['updated_at'] = datetime.now().isoformat()
    s = ', '.join(f'{k} = ?' for k in fields)
    with get_db() as conn: conn.execute(f'UPDATE campaigns SET {s} WHERE id = ?', list(fields.values()) + [cid])

def delete_campaign(cid):
    with get_db() as conn: conn.execute('DELETE FROM campaigns WHERE id = ?', (cid,))

def list_campaigns(onboarding_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM campaigns WHERE onboarding_id = ? ORDER BY created_at DESC', (onboarding_id,)).fetchall()]

def get_campaign(cid):
    with get_db() as conn:
        r = conn.execute('SELECT * FROM campaigns WHERE id = ?', (cid,)).fetchone()
        return dict(r) if r else None


# ---- Personas ----

def create_persona(onboarding_id, agency_id, **kwargs):
    pid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO personas (id, onboarding_id, agency_id, name, age_range, job_title, location, income, bio, goals, pain_points, channels, brands, buying_behavior, messaging_angle, color, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (pid, onboarding_id, agency_id, kwargs.get('name',''), kwargs.get('age_range',''), kwargs.get('job_title',''), kwargs.get('location',''), kwargs.get('income',''), kwargs.get('bio',''), kwargs.get('goals',''), kwargs.get('pain_points',''), kwargs.get('channels',''), kwargs.get('brands',''), kwargs.get('buying_behavior',''), kwargs.get('messaging_angle',''), kwargs.get('color','#667eea'), now, now),
        )
    return pid

def update_persona(pid, **kwargs):
    allowed = {'name','age_range','job_title','location','income','bio','goals','pain_points','channels','brands','buying_behavior','messaging_angle','color'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    fields['updated_at'] = datetime.now().isoformat()
    s = ', '.join(f'{k} = ?' for k in fields)
    with get_db() as conn: conn.execute(f'UPDATE personas SET {s} WHERE id = ?', list(fields.values()) + [pid])

def delete_persona(pid):
    with get_db() as conn: conn.execute('DELETE FROM personas WHERE id = ?', (pid,))

def list_personas(onboarding_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM personas WHERE onboarding_id = ? ORDER BY created_at', (onboarding_id,)).fetchall()]

def get_persona(pid):
    with get_db() as conn:
        r = conn.execute('SELECT * FROM personas WHERE id = ?', (pid,)).fetchone()
        return dict(r) if r else None


# ---- Copy Library ----

def create_copy(onboarding_id, agency_id, **kwargs):
    cid = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO copy_library (id, onboarding_id, agency_id, platform, content_type, topic, copy_text, hashtags, is_favorite, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (cid, onboarding_id, agency_id, kwargs.get('platform',''), kwargs.get('content_type',''), kwargs.get('topic',''), kwargs.get('copy_text',''), kwargs.get('hashtags',''), 0, datetime.now().isoformat()),
        )
    return cid

def delete_copy(cid):
    with get_db() as conn: conn.execute('DELETE FROM copy_library WHERE id = ?', (cid,))

def toggle_copy_favorite(cid):
    with get_db() as conn:
        r = conn.execute('SELECT is_favorite FROM copy_library WHERE id = ?', (cid,)).fetchone()
        if r:
            conn.execute('UPDATE copy_library SET is_favorite = ? WHERE id = ?', (0 if r['is_favorite'] else 1, cid))

def list_copies(onboarding_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM copy_library WHERE onboarding_id = ? ORDER BY is_favorite DESC, created_at DESC', (onboarding_id,)).fetchall()]

def get_copy(cid):
    with get_db() as conn:
        r = conn.execute('SELECT * FROM copy_library WHERE id = ?', (cid,)).fetchone()
        return dict(r) if r else None


# ---- SEO Keywords ----

def create_seo_keyword(onboarding_id, agency_id, **kwargs):
    kid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO seo_keywords (id, onboarding_id, agency_id, keyword, cluster, search_volume, difficulty, intent, priority, status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (kid, onboarding_id, agency_id, kwargs.get('keyword',''), kwargs.get('cluster',''), kwargs.get('search_volume',''), kwargs.get('difficulty',''), kwargs.get('intent',''), kwargs.get('priority','medium'), kwargs.get('status','research'), kwargs.get('notes',''), now, now),
        )
    return kid

def update_seo_keyword(kid, **kwargs):
    allowed = {'keyword','cluster','search_volume','difficulty','intent','priority','status','notes'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    fields['updated_at'] = datetime.now().isoformat()
    s = ', '.join(f'{k} = ?' for k in fields)
    with get_db() as conn: conn.execute(f'UPDATE seo_keywords SET {s} WHERE id = ?', list(fields.values()) + [kid])

def delete_seo_keyword(kid):
    with get_db() as conn: conn.execute('DELETE FROM seo_keywords WHERE id = ?', (kid,))

def list_seo_keywords(onboarding_id):
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM seo_keywords WHERE onboarding_id = ? ORDER BY cluster, priority DESC, created_at', (onboarding_id,)).fetchall()]

def get_seo_keyword(kid):
    with get_db() as conn:
        r = conn.execute('SELECT * FROM seo_keywords WHERE id = ?', (kid,)).fetchone()
        return dict(r) if r else None


def save_tool_output(onboarding_id, agency_id, tool_type, title, prompt, output):
    record_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            'INSERT INTO tool_outputs (id, onboarding_id, agency_id, tool_type, title, prompt, output, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (record_id, onboarding_id, agency_id, tool_type, title, prompt, output, datetime.now().isoformat()),
        )
    return record_id


def list_tool_outputs(onboarding_id, tool_type):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM tool_outputs WHERE onboarding_id = ? AND tool_type = ? ORDER BY created_at DESC',
            (onboarding_id, tool_type),
        ).fetchall()
        return [dict(r) for r in rows]


def get_tool_output(output_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM tool_outputs WHERE id = ?', (output_id,)).fetchone()
        return dict(row) if row else None


def delete_tool_output(output_id):
    with get_db() as conn:
        conn.execute('DELETE FROM tool_outputs WHERE id = ?', (output_id,))


def count_tool_outputs(onboarding_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT tool_type, COUNT(*) as c FROM tool_outputs WHERE onboarding_id = ? GROUP BY tool_type',
            (onboarding_id,),
        ).fetchall()
        return {r['tool_type']: r['c'] for r in rows}


def list_onboardings_by_agency(agency_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM onboardings WHERE agency_id = ? ORDER BY created_at DESC', (agency_id,)
        ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r['data'] = json.loads(r['data'])
            results.append(r)
        return results


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


# ---- Seed Defaults ----

def seed_agency_defaults(agency_id):
    """Seed default form sections, questions, and document templates for a new agency."""
    sections = {}

    # --- Section 1: Basic Information ---
    sid = create_form_section(agency_id, 'Basic Information', 'Tell us about your company', sort_order=1, is_default=1)
    sections['basic_info'] = sid
    for label, key, ftype, opts, req, ph, order in [
        ('Company Name', 'full_name', 'text', '[]', 1, 'Acme Corp', 1),
        ('Email Address', 'email', 'email', '[]', 1, 'jane@acmecorp.com', 2),
        ('Phone Number', 'phone', 'phone', '[]', 0, '(555) 123-4567', 3),
        ('Website URL', 'website', 'url', '[]', 0, 'https://acmecorp.com', 4),
        ('Primary Contact Name', 'manager_name', 'text', '[]', 0, 'Jane Smith', 5),
    ]:
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
        json.dumps(['HubSpot', 'Salesforce', 'Pipedrive', 'Zoho', 'None', 'Other']), 0, '', 1)
    create_form_question(sid, agency_id, 'Project / Task Management', 'pm_tools', 'multiselect',
        json.dumps(['ClickUp', 'Asana', 'Monday', 'Trello', 'Notion', 'None', 'Other']), 0, '', 2)
    create_form_question(sid, agency_id, 'Email Marketing', 'email_tools', 'multiselect',
        json.dumps(['Mailchimp', 'ConvertKit', 'ActiveCampaign', 'Klaviyo', 'None', 'Other']), 0, '', 3)
    create_form_question(sid, agency_id, 'Social Media Management', 'social_tools', 'multiselect',
        json.dumps(['Hootsuite', 'Buffer', 'Sprout Social', 'Later', 'None', 'Other']), 0, '', 4)
    create_form_question(sid, agency_id, 'Analytics / Reporting', 'analytics_tools', 'multiselect',
        json.dumps(['Google Analytics', 'SEMrush', 'Ahrefs', 'None', 'Other']), 0, '', 5)
    create_form_question(sid, agency_id, 'AI Tools', 'ai_tools', 'multiselect',
        json.dumps(['ChatGPT', 'Claude', 'Jasper', 'None', 'Other']), 0, '', 6)

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
        json.dumps(['ASAP', '1-2 Weeks', '1 Month', '2-3 Months', 'Flexible']), 0, 'Select timeline...', 2)
    create_form_question(sid, agency_id, 'Required Integrations', 'integrations', 'textarea', '[]', 0, 'Any tools or platforms that need to be integrated?', 3)

    # --- Section 8: Communication Preferences ---
    sid = create_form_section(agency_id, 'Communication Preferences', 'How should we stay in touch?', sort_order=8, is_default=1)
    sections['communication'] = sid
    create_form_question(sid, agency_id, 'Meeting Frequency', 'meeting_frequency', 'select',
        json.dumps(['Weekly', 'Bi-weekly', 'Monthly', 'As Needed']), 0, 'Select frequency...', 1)
    create_form_question(sid, agency_id, 'Preferred Communication Tools', 'communication_tools', 'multiselect',
        json.dumps(['Email', 'Slack', 'Video Calls', 'Phone', 'WhatsApp']), 0, '', 2)
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


def migrate_agencies_table():
    """Add new columns to agencies table if they don't exist (for existing databases)."""
    new_columns = {
        'airtable_token': "TEXT DEFAULT ''",
        'airtable_base_id': "TEXT DEFAULT ''",
        'airtable_table_id': "TEXT DEFAULT ''",
    }
    with get_db() as conn:
        existing = {row[1] for row in conn.execute('PRAGMA table_info(agencies)').fetchall()}
        for col, col_type in new_columns.items():
            if col not in existing:
                conn.execute(f'ALTER TABLE agencies ADD COLUMN {col} {col_type}')
                logger.info(f'Added column agencies.{col}')


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


def get_agency_form_config(agency_id):
    """Return all enabled sections with their enabled questions, ordered."""
    sections = list_form_sections(agency_id, enabled_only=True)
    for section in sections:
        section['questions'] = list_form_questions(section['id'], enabled_only=True)
    return sections
