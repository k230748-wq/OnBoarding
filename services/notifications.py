import os
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.logger import setup_logger

logger = setup_logger()


class NotificationService:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.notification_email = os.getenv('NOTIFICATION_EMAIL', self.smtp_user)
        self.agency_name = os.getenv('AGENCY_NAME', 'Our Agency')

        if not self.smtp_user or not self.smtp_password:
            raise ValueError('SMTP credentials not configured')

    def _send_email(self, to_email, subject, html_body, retries=3):
        for attempt in range(retries):
            try:
                msg = MIMEMultipart('alternative')
                msg['From'] = f'{self.agency_name} <{self.smtp_user}>'
                msg['To'] = to_email
                msg['Subject'] = subject
                msg.attach(MIMEText(html_body, 'html'))

                if self.smtp_port == 465:
                    with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                        server.login(self.smtp_user, self.smtp_password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                        server.starttls()
                        server.login(self.smtp_user, self.smtp_password)
                        server.send_message(msg)

                logger.info(f'Email sent to {to_email}: {subject}')
                return True
            except Exception as e:
                logger.error(f'Email attempt {attempt + 1} failed: {e}')
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return False

    def send_email(self, to_email, subject, body):
        """Public method for sending a plain-text email wrapped in a simple HTML template."""
        paragraphs = ''.join(f'<p style="margin:0 0 12px;color:#333;font-size:15px;line-height:1.6;">{line}</p>' for line in body.split('\n') if line.strip())
        html = f'''<div style="max-width:600px;margin:20px auto;font-family:-apple-system,sans-serif;">
            <h2 style="color:#1a1a2e;font-size:20px;margin-bottom:16px;">{subject}</h2>
            {paragraphs}
            <p style="color:#aaa;font-size:12px;margin-top:24px;">Sent via {self.agency_name}</p>
        </div>'''
        return self._send_email(to_email, subject, html)

    def _build_email_html(self, title, content_blocks):
        blocks_html = ''
        for block in content_blocks:
            btype = block.get('type', 'paragraph')
            content = block.get('content', '')

            if btype == 'heading':
                level = block.get('level', 2)
                sizes = {1: '28px', 2: '22px', 3: '18px'}
                size = sizes.get(level, '18px')
                blocks_html += f'<h{level} style="color:#333;font-size:{size};margin:20px 0 10px;">{content}</h{level}>'
            elif btype == 'paragraph':
                blocks_html += f'<p style="color:#555;font-size:15px;line-height:1.7;margin:10px 0;">{content}</p>'
            elif btype == 'bullet_list':
                items = ''.join(f'<li style="margin:5px 0;color:#555;">{item}</li>' for item in content)
                blocks_html += f'<ul style="padding-left:20px;margin:10px 0;">{items}</ul>'
            elif btype == 'numbered_list':
                items = ''.join(f'<li style="margin:5px 0;color:#555;">{item}</li>' for item in content)
                blocks_html += f'<ol style="padding-left:20px;margin:10px 0;">{items}</ol>'
            elif btype == 'important':
                blocks_html += (
                    f'<div style="background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;'
                    f'margin:15px 0;border-radius:4px;"><strong style="color:#856404;">⚠️ Important:</strong> '
                    f'<span style="color:#856404;">{content}</span></div>'
                )
            elif btype == 'tip':
                blocks_html += (
                    f'<div style="background:#d4edda;border-left:4px solid #28a745;padding:12px 16px;'
                    f'margin:15px 0;border-radius:4px;"><strong style="color:#155724;">💡 Tip:</strong> '
                    f'<span style="color:#155724;">{content}</span></div>'
                )
            elif btype == 'info':
                blocks_html += (
                    f'<div style="background:#d1ecf1;border-left:4px solid #17a2b8;padding:12px 16px;'
                    f'margin:15px 0;border-radius:4px;"><strong style="color:#0c5460;">ℹ️ Info:</strong> '
                    f'<span style="color:#0c5460;">{content}</span></div>'
                )
            elif btype == 'divider':
                blocks_html += '<hr style="border:none;border-top:1px solid #eee;margin:25px 0;">'

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
  <tr><td style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px 40px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:24px;">{self.agency_name}</h1>
    <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">{title}</p>
  </td></tr>
  <tr><td style="padding:30px 40px;">
    {blocks_html}
  </td></tr>
  <tr><td style="background:#f8f9fa;padding:20px 40px;text-align:center;">
    <p style="color:#999;font-size:12px;margin:0;">© {self.agency_name} | This is an automated onboarding email</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    def _markdown_to_blocks(self, markdown_text):
        blocks = []
        lines = markdown_text.strip().split('\n')
        current_list = []
        list_type = None

        def flush_list():
            nonlocal current_list, list_type
            if current_list:
                blocks.append({'type': list_type, 'content': current_list})
                current_list = []
                list_type = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush_list()
                continue

            # Headers
            header_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
            if header_match:
                flush_list()
                level = len(header_match.group(1))
                blocks.append({'type': 'heading', 'level': level, 'content': header_match.group(2)})
                continue

            # Bullet list
            bullet_match = re.match(r'^[-*]\s+(.+)$', stripped)
            if bullet_match:
                if list_type != 'bullet_list':
                    flush_list()
                    list_type = 'bullet_list'
                current_list.append(bullet_match.group(1))
                continue

            # Numbered list
            num_match = re.match(r'^\d+[.)]\s+(.+)$', stripped)
            if num_match:
                if list_type != 'numbered_list':
                    flush_list()
                    list_type = 'numbered_list'
                current_list.append(num_match.group(1))
                continue

            # Horizontal rule
            if re.match(r'^---+$', stripped):
                flush_list()
                blocks.append({'type': 'divider'})
                continue

            # Regular paragraph
            flush_list()
            # Convert markdown bold
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            blocks.append({'type': 'paragraph', 'content': text})

        flush_list()
        return blocks

    def send_employee_welcome_email(self, data, onboarding_id, dashboard_url=''):
        dashboard_link = dashboard_url or f'/dashboard/{onboarding_id}'
        blocks = [
            {'type': 'heading', 'level': 2, 'content': f'Welcome, {data.get("full_name", "Valued Client")}!'},
            {'type': 'paragraph', 'content': f'We\'re thrilled to officially welcome you to {self.agency_name}. Your onboarding process has been initiated and our team is already preparing everything for your project launch.'},
            {'type': 'info', 'content': f'Your Onboarding ID: <strong>{onboarding_id}</strong>'},
            {'type': 'heading', 'level': 3, 'content': 'What Happens Next'},
            {'type': 'bullet_list', 'content': [
                'Your project workspace is being set up in our management tools',
                'Personalized onboarding documents are being generated',
                'Your dedicated account team is being assembled',
                'You\'ll receive additional emails with your onboarding materials',
            ]},
            {'type': 'tip', 'content': f'Access your client dashboard anytime at: <a href="{dashboard_link}" style="color:#155724;">Client Dashboard</a>'},
            {'type': 'divider'},
            {'type': 'paragraph', 'content': f'If you have any questions, don\'t hesitate to reach out. We\'re here to make this partnership a huge success!'},
            {'type': 'paragraph', 'content': f'Best regards,<br>The {self.agency_name} Team'},
        ]
        html = self._build_email_html('Welcome to Your Onboarding', blocks)
        return self._send_email(data['email'], f'Welcome to {self.agency_name}! 🚀', html)

    def send_manager_notification(self, data, onboarding_id, dashboard_url=''):
        dashboard_link = dashboard_url or f'/dashboard/{onboarding_id}'
        blocks = [
            {'type': 'heading', 'level': 2, 'content': 'New Client Onboarding Started'},
            {'type': 'paragraph', 'content': f'A new client onboarding has been initiated. Here are the details:'},
            {'type': 'bullet_list', 'content': [
                f'<strong>Company:</strong> {data.get("full_name", "N/A")}',
                f'<strong>Contact:</strong> {data.get("manager_name", "N/A")}',
                f'<strong>Service:</strong> {data.get("role", "N/A").replace("_", " ").title()}',
                f'<strong>Start Date:</strong> {data.get("start_date", "N/A")}',
                f'<strong>Onboarding ID:</strong> {onboarding_id}',
            ]},
            {'type': 'info', 'content': f'Dashboard: <a href="{dashboard_link}">View Dashboard</a>'},
        ]
        html = self._build_email_html('New Client Onboarding', blocks)
        return self._send_email(
            data.get('manager_email', self.notification_email),
            f'New Client Onboarding: {data.get("full_name", "New Client")}',
            html,
        )

    def send_admin_alert(self, onboarding_id, error_message):
        blocks = [
            {'type': 'heading', 'level': 2, 'content': '⚠️ Onboarding Error'},
            {'type': 'important', 'content': f'An error occurred during onboarding <strong>{onboarding_id}</strong>.'},
            {'type': 'paragraph', 'content': f'<strong>Error:</strong> {error_message}'},
            {'type': 'paragraph', 'content': 'Please investigate and take corrective action.'},
        ]
        html = self._build_email_html('Onboarding Error Alert', blocks)
        return self._send_email(
            self.notification_email,
            f'⚠️ Onboarding Error: {onboarding_id}',
            html,
        )

    def _send_ai_document_email(self, data, content, doc_title, subject):
        blocks = self._markdown_to_blocks(content)
        html = self._build_email_html(doc_title, blocks)
        return self._send_email(data['email'], subject, html)

    def send_ai_document_email(self, data, content, doc_title='Document'):
        subject = f'{self.agency_name} - {doc_title}'
        return self._send_ai_document_email(data, content, doc_title, subject)

