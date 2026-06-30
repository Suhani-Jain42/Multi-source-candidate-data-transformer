"""
Normalization utilities.

Design decision: we do NOT pull in a heavyweight phone-parsing library.
This environment has no package index access, and pulling region metadata
correctly is itself a deep rabbit hole. Instead we implement a small,
deterministic, documented heuristic E.164 normalizer that:
  - strips formatting
  - assumes a configurable default country code when none is present
  - never invents digits, only reformats what's given
This is called out explicitly as an edge case / known limitation in the
design doc (Step 1).
"""
from __future__ import annotations
import re
from datetime import datetime

DEFAULT_COUNTRY_CALLING_CODE = "91"  # documented assumption: default to India if no + prefix

# Minimal country name/alias -> ISO-3166 alpha-2 map. Extend as needed.
COUNTRY_ALPHA2 = {
    "india": "IN", "in": "IN",
    "united states": "US", "usa": "US", "us": "US", "united states of america": "US",
    "united kingdom": "GB", "uk": "GB", "england": "GB",
    "canada": "CA", "germany": "DE", "france": "FR", "singapore": "SG",
    "australia": "AU", "netherlands": "NL", "ireland": "IE",
}

# Canonical skill name map: lowercase alias -> canonical display name.
# This is intentionally a small seed list; in production this would be backed
# by a maintained taxonomy service, not a hardcoded dict.
SKILL_CANONICAL = {
    "js": "JavaScript", "javascript": "JavaScript",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "py": "Python", "python": "Python", "python3": "Python",
    "react": "React", "reactjs": "React", "react.js": "React",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "go": "Go", "golang": "Go",
    "ts": "TypeScript", "typescript": "TypeScript",
    "aws": "AWS", "amazon web services": "AWS",
    "sql": "SQL", "c++": "C++", "cpp": "C++",
    "docker": "Docker", "git": "Git", "java": "Java",
}


def normalize_phone(raw: str, default_country_code: str = DEFAULT_COUNTRY_CALLING_CODE) -> tuple[str | None, list[str]]:
    """Best-effort E.164 normalization. Returns (normalized_or_None, warnings)."""
    warnings: list[str] = []
    if not raw or not str(raw).strip():
        return None, ["empty phone value"]
    digits = re.sub(r"[^\d+]", "", str(raw))
    if not digits:
        return None, [f"no digits found in phone value: {raw!r}"]
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("+"):
        normalized = digits
    else:
        digits = digits.lstrip("0")
        if len(digits) <= 10:
            normalized = f"+{default_country_code}{digits}"
            warnings.append(f"no country code present; assumed +{default_country_code}")
        else:
            normalized = f"+{digits}"
    if not re.fullmatch(r"\+\d{8,15}", normalized):
        return None, [f"could not confidently normalize phone: {raw!r}"]
    return normalized, warnings


def normalize_date_to_yyyymm(raw) -> tuple[str | None, list[str]]:
    """Normalize a wide variety of date-ish inputs to 'YYYY-MM'. None/'' -> None."""
    if raw is None:
        return None, []
    s = str(raw).strip()
    if not s or s.lower() in ("present", "current", "ongoing", "now"):
        return None, []
    fmts = ["%Y-%m-%d", "%Y-%m", "%Y/%m", "%m/%Y", "%b %Y", "%B %Y", "%Y"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m"), []
        except ValueError:
            continue
    m = re.match(r"^(\d{4})", s)
    if m:
        return f"{m.group(1)}-01", [f"only year found in date {raw!r}; defaulted month to 01"]
    return None, [f"unparseable date: {raw!r}"]


def normalize_country(raw: str | None) -> tuple[str | None, list[str]]:
    if not raw:
        return None, []
    key = str(raw).strip().lower()
    if key.upper() in COUNTRY_ALPHA2.values():
        return key.upper(), []
    if key in COUNTRY_ALPHA2:
        return COUNTRY_ALPHA2[key], []
    return None, [f"unrecognized country: {raw!r}"]


def normalize_skill(raw: str) -> str:
    key = str(raw).strip().lower()
    return SKILL_CANONICAL.get(key, str(raw).strip().title())


def normalize_email(raw: str) -> tuple[str | None, list[str]]:
    if not raw or not str(raw).strip():
        return None, ["empty email"]
    s = str(raw).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
        return None, [f"malformed email skipped: {raw!r}"]
    return s, []
