"""
Extractor: ATS JSON blob (semi-structured).
Field names do NOT match our canonical names by design (that's the point of
this source type) so this extractor maps several plausible ATS field-name
variants onto our internal RawRecord. Unknown/extra fields are ignored, not
invented. A missing or malformed file degrades to zero records.
"""
from __future__ import annotations
import json
from src.models import RawRecord

# alias maps: canonical_concept -> list of possible ATS json keys (case-insensitive)
ALIASES = {
    "name": ["candidate_name", "name", "full_name", "fullName"],
    "email": ["email_address", "email", "primary_email", "contact_email"],
    "phone": ["mobile", "phone_number", "phone", "contact_number"],
    "company": ["employer", "current_employer", "company", "organization"],
    "title": ["job_title", "role", "title", "position"],
    "headline": ["summary", "headline", "tagline"],
    "city": ["city", "location_city"],
    "country": ["country", "location_country"],
    "skills": ["skills", "tags", "tech_stack"],
}


def _first_match(d: dict, keys: list[str]):
    lower_map = {k.lower(): k for k in d.keys()}
    for k in keys:
        if k.lower() in lower_map:
            return d[lower_map[k.lower()]]
    return None


def extract(path: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return records
    except Exception as e:
        rec = RawRecord(source_id=f"ats_json:{path}", source_type="ats_json")
        rec.errors.append(f"malformed JSON, source skipped: {e}")
        return [rec]

    # Accept either a single object or a list of candidate objects.
    candidates = data if isinstance(data, list) else [data]

    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            continue
        rec = RawRecord(source_id=f"ats_json:item{i}", source_type="ats_json")
        name = _first_match(c, ALIASES["name"])
        email = _first_match(c, ALIASES["email"])
        phone = _first_match(c, ALIASES["phone"])
        company = _first_match(c, ALIASES["company"])
        title = _first_match(c, ALIASES["title"])
        headline = _first_match(c, ALIASES["headline"])
        city = _first_match(c, ALIASES["city"])
        country = _first_match(c, ALIASES["country"])
        skills = _first_match(c, ALIASES["skills"])

        if not any([name, email, phone, company, title]):
            rec.errors.append("ATS item had no recognizable fields, skipped")
            continue

        rec.full_name = str(name).strip() if name else None
        if email:
            rec.emails = [str(email).strip()]
            rec.match_keys["email"] = str(email).strip().lower()
        if phone:
            rec.phones = [str(phone).strip()]
        rec.current_company = str(company).strip() if company else None
        rec.title = str(title).strip() if title else None
        rec.headline = str(headline).strip() if headline else None
        if city or country:
            rec.location = {"city": city, "region": None, "country": country}
        if isinstance(skills, list):
            rec.skills = [str(s) for s in skills]
        elif isinstance(skills, str):
            rec.skills = [s.strip() for s in skills.split(",") if s.strip()]
        if name:
            rec.match_keys.setdefault("name", str(name).strip().lower())
        records.append(rec)
    return records
