"""Markdown document -> styled PDF. Used for CVs and cover notes."""
import re

import markdown
from weasyprint import CSS, HTML

CSS_TEXT = """
@page { size: A4; margin: 16mm 17mm 16mm 17mm; }
body { font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 10pt; line-height: 1.38; color: #1c1c1c; }
h1 { font-size: 20pt; margin: 0 0 2pt 0; letter-spacing: -0.2pt; }
h1 + p { margin: 0 0 2pt 0; }               /* tagline */
h1 + p + p { color: #555; font-size: 9pt; margin: 0 0 10pt 0; }  /* contact line */
h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: 0.6pt; color: #333; margin: 12pt 0 4pt 0; padding-bottom: 2pt; border-bottom: 0.6pt solid #bbb; }
h3 { font-size: 10.5pt; margin: 9pt 0 1pt 0; }
h3 + p { color: #555; font-size: 9pt; margin: 0 0 3pt 0; }
p { margin: 0 0 5pt 0; }
ul { margin: 0 0 4pt 0; padding-left: 14pt; }
li { margin: 0 0 2.5pt 0; }
strong { font-weight: 600; }
blockquote { margin: 0 0 8pt 0; padding: 4pt 8pt; border-left: 2pt solid #d9a441; color: #555; font-size: 9pt; }
a { color: inherit; text-decoration: none; }
"""


def to_pdf(md_text: str) -> bytes:
    body = markdown.markdown(md_text, extensions=["extra", "sane_lists"])
    html = f"<!doctype html><html><head><meta charset='utf-8'></head><body>{body}</body></html>"
    return HTML(string=html).write_pdf(stylesheets=[CSS(string=CSS_TEXT)])


def filename(kind: str, company: str | None, title: str | None) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{company or ''}-{title or ''}").strip("-")[:60]
    label = {"cv": "CV", "cover": "Cover-note", "prep": "Interview-prep"}.get(kind, kind)
    return f"Steve-Hunter-{label}-{slug}.pdf" if slug else f"Steve-Hunter-{label}.pdf"
