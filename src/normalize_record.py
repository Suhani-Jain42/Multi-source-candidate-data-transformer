"""
Stage 2: normalize.

Applies normalization helpers to every RawRecord produced by extractors.
Normalization warnings get attached to rec.errors (used later for
confidence scoring) but never drop the record - "robust" constraint.
"""
from __future__ import annotations
from src.models import RawRecord
from src import normalize as N


def normalize_record(rec: RawRecord) -> RawRecord:
    norm_emails = []
    for e in rec.emails:
        v, warns = N.normalize_email(e)
        rec.errors.extend(warns)
        if v:
            norm_emails.append(v)
    rec.emails = norm_emails

    norm_phones = []
    for p in rec.phones:
        v, warns = N.normalize_phone(p)
        rec.errors.extend(warns)
        if v:
            norm_phones.append(v)
    rec.phones = norm_phones

    if rec.location:
        country, warns = N.normalize_country(rec.location.get("country"))
        rec.errors.extend(warns)
        rec.location["country"] = country

    rec.skills = [N.normalize_skill(s) for s in rec.skills if s and str(s).strip()]

    norm_exp = []
    for e in rec.experience:
        e = dict(e)
        start, w1 = N.normalize_date_to_yyyymm(e.get("start"))
        end, w2 = N.normalize_date_to_yyyymm(e.get("end"))
        rec.errors.extend(w1 + w2)
        e["start"], e["end"] = start, end
        norm_exp.append(e)
    rec.experience = norm_exp

    return rec
