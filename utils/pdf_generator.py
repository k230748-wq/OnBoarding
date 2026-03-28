import io
import re

from fpdf import FPDF


class DocumentPDF(FPDF):
    def __init__(self, title='', agency_name=''):
        super().__init__()
        self.doc_title = title
        self.agency_name = agency_name

    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, self.agency_name, align='L')
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(180, 180, 180)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')


def generate_pdf(title, content, agency_name=''):
    """Convert markdown-ish content to a clean PDF. Returns bytes."""
    pdf = DocumentPDF(title=title, agency_name=agency_name)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    lm = pdf.l_margin

    # Title
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(26, 26, 46)
    pdf.cell(0, 14, title, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(6)

    # Divider line
    pdf.set_draw_color(220, 220, 220)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    # Sanitize Unicode characters not supported by Helvetica
    replacements = {'\u2022': '-', '\u2013': '-', '\u2014': '-', '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u00a0': ' '}
    for old, new in replacements.items():
        content = content.replace(old, new)
    content = content.encode('latin-1', errors='replace').decode('latin-1')

    # Parse content line by line
    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()

        if not stripped:
            pdf.ln(4)
            continue

        # Heading ##
        if stripped.startswith('## '):
            pdf.ln(4)
            pdf.set_font('Helvetica', 'B', 15)
            pdf.set_text_color(26, 26, 46)
            text = stripped[3:].strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            pdf.set_x(lm)
            pdf.multi_cell(0, 10, text)
            pdf.ln(2)
            continue

        # Heading ###
        if stripped.startswith('### '):
            pdf.ln(2)
            pdf.set_font('Helvetica', 'B', 13)
            pdf.set_text_color(60, 60, 80)
            text = stripped[4:].strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            pdf.set_x(lm)
            pdf.multi_cell(0, 9, text)
            pdf.ln(1)
            continue

        # Heading #
        if stripped.startswith('# '):
            pdf.ln(4)
            pdf.set_font('Helvetica', 'B', 17)
            pdf.set_text_color(26, 26, 46)
            text = stripped[2:].strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            pdf.set_x(lm)
            pdf.multi_cell(0, 11, text)
            pdf.ln(2)
            continue

        # Bullet point
        if stripped.startswith('- ') or stripped.startswith('* '):
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(80, 80, 80)
            text = stripped[2:].strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            pdf.set_x(lm)
            pdf.multi_cell(0, 7, f"    -  {text}")
            continue

        # Numbered list
        num_match = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if num_match:
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(80, 80, 80)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', num_match.group(2))
            pdf.set_x(lm)
            pdf.multi_cell(0, 7, f"    {num_match.group(1)}.  {text}")
            continue

        # Horizontal rule
        if stripped in ('---', '***', '___'):
            pdf.set_draw_color(220, 220, 220)
            pdf.line(lm, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(6)
            continue

        # Regular paragraph
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(60, 60, 60)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
        pdf.set_x(lm)
        pdf.multi_cell(0, 7, text)
        pdf.ln(2)

    # Return as bytes
    return pdf.output()
