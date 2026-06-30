"""
Extractor: recruiter notes (.txt) - unstructured free text.

Recruiter notes are messy prose, e.g.:
    "Spoke with Priya Sharma (priya.sharma@gmail.com, +91 98765 43210) -
    ~5 yrs exp, strong in Python/Django, currently at Zomato as Backend
    Engineer. Based in Bengaluru, India."

We do lightweight, deterministic regex/heuristic extraction rather than
calling an NLP model: it's explainable and reproducible (constraint:
deterministic & explainable), at the cost of recall on very irregular notes
- a tradeoff explicitly called out in the design doc.
"""
from __future__ import annotations
import re
from src.models import RawRecord

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
YEARS_EXP_RE = re.compile(r"(~?\d+(?:\.\d+)?)\s*\+?\s*(?:yrs?|years?)\s*(?:of\s*)?exp", re.IGNORECASE)
AT_COMPANY_RE = re.compile(r"(?:at|with)\s+([A-Z][A-Za-z0-9&.\- ]{1,40}?)\s+as\s+([A-Za-z0-9&/\- ]{1,50}?)(?=[.,]|\s+(?:Based|Based in|Located|Seemed)|$)", re.IGNORECASE)
BASED_IN_RE = re.compile(r"(?:based in|located in|location:)\s*([A-Za-z ,]+)", re.IGNORECASE)


def extract(path: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return records
    except Exception as e:
        rec = RawRecord(source_id=f"notes:{path}", source_type="notes")
        rec.errors.append(f"failed to read notes file: {e}")
        return [rec]

    if not text.strip():
        return records

    # Notes files may contain one block per candidate, separated by blank lines.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    for i, block in enumerate(blocks):
        rec = RawRecord(source_id=f"notes:block{i}", source_type="notes")

        emails = EMAIL_RE.findall(block)
        phones = PHONE_RE.findall(block)
        years_m = YEARS_EXP_RE.search(block)
        company_m = AT_COMPANY_RE.search(block)
        loc_m = BASED_IN_RE.search(block)

        # Name heuristic: first capitalized 2-3 word sequence before a comma/paren.
        name_m = re.match(r"^[^()\n]*?([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})", block)

        if emails:
            rec.emails = [emails[0]]
            rec.match_keys["email"] = emails[0].lower()
        if phones:
            rec.phones = [phones[0].strip()]
        if name_m:
            rec.full_name = name_m.group(1)
            rec.match_keys.setdefault("name", rec.full_name.lower())
        if years_m:
            try:
                rec.years_experience = float(years_m.group(1).replace("~", ""))
            except ValueError:
                pass
        if company_m:
            rec.current_company = company_m.group(1).strip()
            rec.title = company_m.group(2).strip()
        if loc_m:
            city = loc_m.group(1).split(",")[0].strip()
            country = loc_m.group(1).split(",")[-1].strip() if "," in loc_m.group(1) else None
            rec.location = {"city": city, "region": None, "country": country}

        # Skill heuristic: look for "strong in X/Y/Z" or "skills: a, b, c"
        skills_m = re.search(
            r"(?:strong in|skilled in|skills?:)\s*([A-Za-z0-9+/ &-]+(?:[,/][A-Za-z0-9+/ &-]+)*?)"
            r"(?:,\s*(?:currently|based|now|recently|seemed)|\s*[.;]|$)",
            block, re.IGNORECASE,
        )
        if skills_m:
            raw = re.split(r"[,/]| and ", skills_m.group(1))
            rec.skills = [s.strip().rstrip(".") for s in raw if s.strip()]

        rec.notes = [block]
        if not any([rec.emails, rec.phones, rec.full_name, rec.skills, rec.current_company]):
            rec.errors.append("could not extract any structured signal from notes block")
            continue
        records.append(rec)
    return records
