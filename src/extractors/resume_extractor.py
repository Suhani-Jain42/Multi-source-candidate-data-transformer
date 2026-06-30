"""
Extractor: resume file (PDF / DOCX) - unstructured prose.

Same philosophy as notes_extractor: deterministic regex/heuristics over the
extracted text layer, not a generative model, so results are reproducible.
Resumes are richer than notes so we also try to pull an education block.
"""
from __future__ import annotations
import re
from src.models import RawRecord

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
EDU_RE = re.compile(
    r"(B\.?Tech|M\.?Tech|B\.?E\.?|M\.?S\.?|B\.?S\.?|MBA|Ph\.?D|Bachelor[s]?|Master[s]?)[^\n,]{0,60}"
    r"(?:in\s+([A-Za-z &]+))?[^\n]*?(\d{4})",
    re.IGNORECASE,
)


def _read_pdf(path: str) -> str:
    import pdfplumber
    text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text.append(t)
    return "\n".join(text)


def _read_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract(path: str) -> list[RawRecord]:
    rec = RawRecord(source_id=f"resume:{path.split('/')[-1]}", source_type="resume")
    try:
        if path.lower().endswith(".pdf"):
            text = _read_pdf(path)
        elif path.lower().endswith(".docx"):
            text = _read_docx(path)
        else:
            rec.errors.append("unsupported resume file extension")
            return [rec]
    except FileNotFoundError:
        return []
    except Exception as e:
        rec.errors.append(f"failed to extract text from resume: {e}")
        return [rec]

    if not text.strip():
        rec.errors.append("resume produced no extractable text (possibly scanned/image-based)")
        return [rec]

    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    if emails:
        rec.emails = [emails[0]]
        rec.match_keys["email"] = emails[0].lower()
    if phones:
        rec.phones = [phones[0].strip()]

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        if re.fullmatch(r"[A-Za-z .'-]{3,50}", first) and not EMAIL_RE.search(first):
            rec.full_name = first
            rec.match_keys.setdefault("name", first.lower())

    edu_matches = EDU_RE.findall(text)
    for degree, fld, year in edu_matches:
        rec.education.append({
            "institution": None,
            "degree": degree,
            "field": fld.strip() if fld else None,
            "end_year": year,
        })

    skills_section = re.search(r"(?:Skills|Technical Skills)\s*[:\n]([^\n]+(?:\n[^\n]+)?)", text, re.IGNORECASE)
    if skills_section:
        raw = re.split(r"[,|/]", skills_section.group(1))
        rec.skills = [s.strip() for s in raw if s.strip() and len(s.strip()) < 30]

    headline_m = re.search(r"(Software Engineer|Backend Engineer|Frontend Engineer|Data Scientist|Full[ -]?Stack Engineer|Product Manager)[^\n]*", text, re.IGNORECASE)
    if headline_m:
        rec.headline = headline_m.group(0).strip()

    if not any([rec.emails, rec.phones, rec.full_name, rec.skills, rec.education]):
        rec.errors.append("could not extract structured signal from resume text")
    return [rec]
