"""
Builds the DEFAULT OUTPUT SCHEMA dict (the one in the assignment's table)
from the internal CanonicalProfile. This is the one clean boundary between
"how we modeled things internally" and "what the contract with downstream
consumers looks like" - the projection layer (project.py) only ever talks
to this dict, never to internal dataclasses, keeping that separation clean
as required.
"""
from __future__ import annotations
from src.models import CanonicalProfile


def build_default_output(profile: CanonicalProfile) -> dict:
    out = {
        "candidate_id": profile.candidate_id,
        "full_name": profile.full_name.value if profile.full_name else None,
        "emails": [fv.value for fv in profile.emails],
        "phones": [fv.value for fv in profile.phones],
        "location": profile.location.value if profile.location else {"city": None, "region": None, "country": None},
        "links": {
            "linkedin": profile.links.get("linkedin").value if "linkedin" in profile.links else None,
            "github": profile.links.get("github").value if "github" in profile.links else None,
            "portfolio": profile.links.get("portfolio").value if "portfolio" in profile.links else None,
            "other": [v.value for k, v in profile.links.items() if k not in ("linkedin", "github", "portfolio")],
        },
        "headline": profile.headline.value if profile.headline else None,
        "years_experience": profile.years_experience.value if profile.years_experience else None,
        "skills": [
            {"name": fv.value, "confidence": fv.confidence, "sources": fv.sources}
            for fv in profile.skills
        ],
        "experience": [fv.value for fv in profile.experience],
        "education": [fv.value for fv in profile.education],
        "provenance": [
            {"field": p.field, "source": p.source, "method": p.method}
            for p in profile.provenance
        ],
        "overall_confidence": profile.overall_confidence,
    }
    return out
