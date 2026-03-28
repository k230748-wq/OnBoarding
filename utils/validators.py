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


VALID_ROLES = [
    'social_media', 'content_marketing', 'paid_ads', 'seo', 'branding'
]


def validate_onboarding_data(data, required_fields=None):
    """Validate onboarding form data.

    If required_fields is provided (list of dicts with 'field_key', 'field_type', 'label'),
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
        # Legacy fallback
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
