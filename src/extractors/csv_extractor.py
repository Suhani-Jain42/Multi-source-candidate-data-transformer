"""
Extractor: Recruiter CSV export (structured).
Expected columns (case-insensitive, order-independent): name, email, phone,
current_company, title. Missing columns -> missing fields, never a crash.
"""
from __future__ import annotations
import csv
from src.models import RawRecord


def extract(path: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return records
            fieldmap = {fn.strip().lower(): fn for fn in reader.fieldnames}

            def get(row, key):
                col = fieldmap.get(key)
                if col is None:
                    return None
                val = row.get(col)
                return val.strip() if isinstance(val, str) else val

            for i, row in enumerate(reader):
                rec = RawRecord(
                    source_id=f"recruiter_csv:row{i+2}",  # +2: header is row1, 1-indexed data
                    source_type="recruiter_csv",
                )
                name = get(row, "name") or get(row, "full_name")
                email = get(row, "email")
                phone = get(row, "phone")
                company = get(row, "current_company") or get(row, "company")
                title = get(row, "title")

                if not any([name, email, phone, company, title]):
                    rec.errors.append("entirely empty row, skipped")
                    continue

                rec.full_name = name or None
                if email:
                    rec.emails = [email]
                    rec.match_keys["email"] = email.lower()
                if phone:
                    rec.phones = [phone]
                rec.current_company = company or None
                rec.title = title or None
                if name:
                    rec.match_keys.setdefault("name", name.strip().lower())
                records.append(rec)
    except FileNotFoundError:
        pass  # robustness constraint: missing source -> no records, not a crash
    except Exception as e:
        rec = RawRecord(source_id=f"recruiter_csv:{path}", source_type="recruiter_csv")
        rec.errors.append(f"failed to parse CSV: {e}")
        records.append(rec)
    return records
