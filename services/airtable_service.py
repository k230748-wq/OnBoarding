import time

from pyairtable import Api

from utils.logger import setup_logger

logger = setup_logger()


# Field schema for the Clients table that gets auto-created in the agency's Airtable base
CLIENTS_TABLE_FIELDS = [
    {'name': 'Company Name', 'type': 'singleLineText'},
    {'name': 'Email', 'type': 'email'},
    {'name': 'Phone', 'type': 'phoneNumber'},
    {'name': 'Website', 'type': 'url'},
    {'name': 'Primary Contact', 'type': 'singleLineText'},
    {'name': 'Service Type', 'type': 'singleSelect', 'options': {
        'choices': [
            {'name': 'Social Media', 'color': 'blueLight2'},
            {'name': 'Content Marketing', 'color': 'greenLight2'},
            {'name': 'Paid Ads', 'color': 'redLight2'},
            {'name': 'SEO', 'color': 'yellowLight2'},
            {'name': 'Branding', 'color': 'purpleLight2'},
        ]
    }},
    {'name': 'Status', 'type': 'singleSelect', 'options': {
        'choices': [
            {'name': 'Onboarding', 'color': 'blueLight2'},
            {'name': 'Active', 'color': 'greenLight2'},
            {'name': 'On Hold', 'color': 'yellowLight2'},
            {'name': 'Completed', 'color': 'grayLight2'},
        ]
    }},
    {'name': 'Onboarding ID', 'type': 'singleLineText'},
    {'name': 'Onboarded At', 'type': 'dateTime', 'options': {'timeZone': 'utc', 'dateFormat': {'name': 'iso'}}},
    {'name': 'Start Date', 'type': 'date', 'options': {'dateFormat': {'name': 'iso'}}},
    {'name': 'Budget Range', 'type': 'singleLineText'},
    {'name': 'Engagement Duration', 'type': 'singleLineText'},
    {'name': 'Business Description', 'type': 'multilineText'},
    {'name': 'Target Market', 'type': 'multilineText'},
    {'name': 'Top Challenges', 'type': 'multilineText'},
    {'name': 'Business Goals', 'type': 'multilineText'},
    {'name': 'Documents Generated', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'Next Meeting', 'type': 'singleLineText'},
    {'name': 'Meeting Topic', 'type': 'singleLineText'},
    {'name': 'Notes', 'type': 'multilineText'},
]

SERVICE_TYPE_MAP = {
    'social_media': 'Social Media',
    'content_marketing': 'Content Marketing',
    'paid_ads': 'Paid Ads',
    'seo': 'SEO',
    'branding': 'Branding',
}


class AirtableService:
    def __init__(self, token, base_id, table_id=''):
        if not token or not base_id:
            raise ValueError('Airtable credentials not configured')
        self.api = Api(token)
        self.base_id = base_id
        self.table_id = table_id
        if table_id:
            self.table = self.api.table(base_id, table_id)
        else:
            self.table = None

    def create_clients_table(self):
        """Create the Clients table in the agency's Airtable base. Returns the table ID."""
        try:
            base = self.api.base(self.base_id)
            new_table = base.create_table('Clients', CLIENTS_TABLE_FIELDS, description='Client onboarding records managed by the onboarding platform.')
            self.table_id = new_table.id
            self.table = self.api.table(self.base_id, new_table.id)
            logger.info(f'Created Airtable Clients table: {new_table.id}')
            return new_table.id
        except Exception as e:
            logger.error(f'Failed to create Airtable table: {e}')
            raise

    def sync_client_record(self, data, onboarding_id):
        """Create or update a client record in Airtable after onboarding."""
        if not self.table:
            logger.warning('Airtable table not configured, skipping sync')
            return None

        service_raw = data.get('role', '')
        service_label = SERVICE_TYPE_MAP.get(service_raw, service_raw.replace('_', ' ').title())

        fields = {
            'Company Name': data.get('full_name', ''),
            'Email': data.get('email', ''),
            'Phone': data.get('phone', ''),
            'Website': data.get('website', ''),
            'Primary Contact': data.get('manager_name', ''),
            'Service Type': service_label if service_label in SERVICE_TYPE_MAP.values() else None,
            'Status': 'Onboarding',
            'Onboarding ID': onboarding_id,
            'Onboarded At': data.get('timestamp', ''),
            'Start Date': data.get('start_date', '') or None,
            'Budget Range': data.get('budget', ''),
            'Engagement Duration': data.get('duration', ''),
            'Business Description': data.get('business_description', ''),
            'Target Market': data.get('target_audience', ''),
            'Top Challenges': data.get('challenges', ''),
            'Business Goals': data.get('goals', ''),
            'Documents Generated': 0,
            'Notes': '',
        }

        # Remove None values to avoid Airtable errors on select fields
        fields = {k: v for k, v in fields.items() if v is not None}

        return self._create_record(fields)

    def update_client_status(self, onboarding_id, status, doc_count=None):
        """Update client status and optionally document count."""
        record = self._find_by_onboarding_id(onboarding_id)
        if not record:
            return None
        updates = {'Status': status}
        if doc_count is not None:
            updates['Documents Generated'] = doc_count
        return self._update_record(record['id'], updates)

    def update_meeting_info(self, onboarding_id, meeting_date, meeting_topic):
        """Update the next meeting info for a client."""
        record = self._find_by_onboarding_id(onboarding_id)
        if not record:
            return None
        return self._update_record(record['id'], {
            'Next Meeting': meeting_date,
            'Meeting Topic': meeting_topic,
        })

    def _find_by_onboarding_id(self, onboarding_id):
        if not self.table:
            return None
        try:
            records = self.table.all(formula=f"{{Onboarding ID}} = '{onboarding_id}'")
            return records[0] if records else None
        except Exception as e:
            logger.error(f'Airtable lookup failed: {e}')
            return None

    def _create_record(self, fields, retries=3):
        for attempt in range(retries):
            try:
                record = self.table.create(fields)
                logger.info(f'Airtable record created: {record.get("id")}')
                return record
            except Exception as e:
                logger.error(f'Airtable create attempt {attempt + 1} failed: {e}')
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def _update_record(self, record_id, updates, retries=3):
        for attempt in range(retries):
            try:
                record = self.table.update(record_id, updates)
                logger.info(f'Airtable record updated: {record_id}')
                return record
            except Exception as e:
                logger.error(f'Airtable update attempt {attempt + 1} failed: {e}')
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise


def get_airtable_for_agency(agency):
    """Create an AirtableService instance for a specific agency, or None if not configured."""
    token = agency.get('airtable_token', '')
    base_id = agency.get('airtable_base_id', '')
    table_id = agency.get('airtable_table_id', '')
    if not token or not base_id:
        return None
    try:
        return AirtableService(token, base_id, table_id)
    except Exception as e:
        logger.warning(f'Airtable init failed for agency {agency.get("id")}: {e}')
        return None
