import os
import time
from datetime import datetime, timedelta

import requests

from utils.logger import setup_logger

logger = setup_logger()


class ClickUpService:
    def __init__(self):
        self.api_token = os.getenv('CLICKUP_API_TOKEN')
        self.team_id = os.getenv('CLICKUP_TEAM_ID')
        self.space_id = os.getenv('CLICKUP_SPACE_ID')

        if not all([self.api_token, self.team_id, self.space_id]):
            raise ValueError('ClickUp credentials not fully configured')

        self.base_url = 'https://api.clickup.com/api/v2'
        self.headers = {
            'Authorization': self.api_token,
            'Content-Type': 'application/json',
        }

    def _request(self, method, endpoint, json=None, retries=3):
        url = f'{self.base_url}/{endpoint}'
        for attempt in range(retries):
            try:
                resp = requests.request(method, url, headers=self.headers, json=json, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f'ClickUp API attempt {attempt + 1} failed: {e}')
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def create_folder(self, folder_name):
        data = self._request('POST', f'space/{self.space_id}/folder', json={'name': folder_name})
        logger.info(f'Created ClickUp folder: {folder_name} (ID: {data.get("id")})')
        return data

    def create_list(self, folder_id, list_name):
        data = self._request('POST', f'folder/{folder_id}/list', json={'name': list_name})
        logger.info(f'Created ClickUp list: {list_name} (ID: {data.get("id")})')
        return data

    def create_task(self, list_id, task_data):
        data = self._request('POST', f'list/{list_id}/task', json=task_data)
        logger.info(f'Created ClickUp task: {task_data.get("name")}')
        return data

    def create_onboarding_tasks(self, client_name, service_type, start_date, contact_name, custom_tasks=None):
        # Create folder
        folder_name = f'{client_name} - Onboarding'
        folder = self.create_folder(folder_name)
        folder_id = folder['id']

        # Create checklist list
        checklist = self.create_list(folder_id, 'Onboarding Checklist')
        list_id = checklist['id']

        # Parse start date
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
        except (ValueError, TypeError):
            start = datetime.now()

        service_label = service_type.replace('_', ' ').title()

        # Define onboarding tasks
        tasks = [
            # Week 1
            {'name': f'Kickoff Call with {contact_name}', 'description': f'Initial kickoff meeting with {client_name} to align on goals, timelines, and expectations for {service_label} services.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=1))},
            {'name': 'Brand Discovery Session', 'description': f'Deep dive into {client_name}\'s brand, voice, target audience, and competitive landscape.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=3))},
            {'name': 'Platform Access & Setup', 'description': 'Collect all platform credentials, set up analytics tracking, and configure project tools.', 'priority': 2, 'due_date': self._to_ms(start + timedelta(days=4))},
            {'name': 'Initial Audit & Analysis', 'description': f'Conduct comprehensive audit of existing {service_label} presence and performance.', 'priority': 2, 'due_date': self._to_ms(start + timedelta(days=5))},
            {'name': 'Competitor Research', 'description': f'Analyze top competitors in {client_name}\'s space for {service_label} benchmarking.', 'priority': 3, 'due_date': self._to_ms(start + timedelta(days=5))},

            # Week 2
            {'name': f'{service_label} Strategy Development', 'description': f'Create comprehensive {service_label} strategy based on discovery and audit findings.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=8))},
            {'name': 'Content Calendar Planning', 'description': 'Develop first month content calendar aligned with strategy and client goals.', 'priority': 2, 'due_date': self._to_ms(start + timedelta(days=10))},
            {'name': 'Strategy Presentation', 'description': f'Present {service_label} strategy to {contact_name} for approval and feedback.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=12))},

            # Week 3-4
            {'name': 'First Campaign/Content Launch', 'description': f'Launch initial {service_label} campaign or content pieces.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=17))},
            {'name': 'Monitoring & Optimization Setup', 'description': 'Configure reporting dashboards and set up performance monitoring.', 'priority': 2, 'due_date': self._to_ms(start + timedelta(days=19))},
            {'name': 'First Progress Report', 'description': 'Compile and deliver first performance and progress report.', 'priority': 2, 'due_date': self._to_ms(start + timedelta(days=21))},

            # Checkpoints
            {'name': '📊 Day 30 Checkpoint Review', 'description': f'30-day performance review for {client_name}. Assess KPIs, adjust strategy, and plan for month 2.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=30))},
            {'name': '📊 Day 60 Checkpoint Review', 'description': f'60-day comprehensive review. Evaluate campaign performance, ROI tracking, and optimization opportunities.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=60))},
            {'name': '📊 Day 90 Comprehensive Review', 'description': f'Quarterly business review with {client_name}. Full performance analysis, strategy refinement, and next quarter planning.', 'priority': 1, 'due_date': self._to_ms(start + timedelta(days=90))},
        ]

        # Add custom service-specific tasks
        if custom_tasks:
            for i, task_name in enumerate(custom_tasks):
                tasks.append({
                    'name': task_name,
                    'description': f'Service-specific task for {service_label}: {task_name}',
                    'priority': 2,
                    'due_date': self._to_ms(start + timedelta(days=7 + i * 3)),
                })

        # Create all tasks
        created = 0
        for task_data in tasks:
            task_data['status'] = 'to do'
            try:
                self.create_task(list_id, task_data)
                created += 1
            except Exception as e:
                logger.error(f'Failed to create task "{task_data["name"]}": {e}')

        list_url = f'https://app.clickup.com/{self.team_id}/v/li/{list_id}'

        return {
            'folder_id': folder_id,
            'list_id': list_id,
            'list_url': list_url,
            'tasks_created': created,
        }

    @staticmethod
    def _to_ms(dt):
        return int(dt.timestamp() * 1000)
