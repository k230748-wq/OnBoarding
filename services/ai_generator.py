import os

from openai import OpenAI

from utils.logger import setup_logger

logger = setup_logger()


class AIGenerator:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError('OPENAI_API_KEY not set')
        self.client = OpenAI(api_key=api_key)

    def _generate_content(self, prompt, max_tokens=2000, agency_name='our agency'):
        try:
            response = self.client.chat.completions.create(
                model='gpt-4',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            f'You are a client success specialist at a marketing agency called {agency_name}. '
                            'Write professional, warm, and actionable content. Use markdown formatting with '
                            'headers (##), bullet points, and bold text for emphasis. Keep the tone collaborative '
                            'and results-oriented.'
                        ),
                    },
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f'AI generation error: {e}')
            raise

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

        return self._generate_content(prompt, max_tokens=2500, agency_name=agency_name)

