"""
Canonical data model for the Multi-Source Candidate Data Transformer.

Design note: this is the INTERNAL representation. It is intentionally richer
than any single output schema (it keeps every value + where it came from +
how confident we are), so the projection layer (project.py) can reshape it
into whatever output schema a runtime config asks for, without ever having
to go back to raw sources.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProvenanceEntry:
    """Where one specific value came from, and how we derived it."""
    field: str                 # canonical field path, e.g. "phones[0]"
    source: str                # source identifier, e.g. "recruiter_csv:row3"
    method: str                # "extracted" | "normalized" | "merged" | "inferred"
    raw_value: Any = None      # original value before normalization (debugging/audit)


@dataclass
class FieldValue:
    """A single normalized value plus the confidence we have in it."""
    value: Any
    confidence: float          # 0.0 - 1.0
    sources: list[str] = field(default_factory=list)  # source ids that support this value


@dataclass
class RawRecord:
    """
    One partial, source-specific view of a candidate, BEFORE merging.
    Every extractor (csv, json, github, resume, notes...) produces a list of
    these. Fields are loosely typed on purpose: extractors only fill in what
    they actually found, never invent values.
    """
    source_id: str             # e.g. "recruiter_csv:row3", "resume:jane.pdf"
    source_type: str           # "recruiter_csv" | "ats_json" | "github" | "linkedin" | "resume" | "notes"
    match_keys: dict[str, str] = field(default_factory=dict)  # e.g. {"email": "...", "name": "..."}
    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: Optional[dict] = None       # {"city":..., "region":..., "country":...}
    links: dict = field(default_factory=dict)  # {"linkedin":..., "github":..., "portfolio":..., "other": []}
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)  # [{company,title,start,end,summary}]
    education: list[dict] = field(default_factory=list)   # [{institution,degree,field,end_year}]
    current_company: Optional[str] = None
    title: Optional[str] = None
    notes: list[str] = field(default_factory=list)        # free-text fragments (recruiter notes)
    errors: list[str] = field(default_factory=list)       # malformed/skip reasons, never crash


@dataclass
class CanonicalProfile:
    """The merged, normalized, fully-provenanced internal profile."""
    candidate_id: str
    full_name: Optional[FieldValue] = None
    emails: list[FieldValue] = field(default_factory=list)
    phones: list[FieldValue] = field(default_factory=list)
    location: Optional[FieldValue] = None
    links: dict[str, FieldValue] = field(default_factory=dict)
    headline: Optional[FieldValue] = None
    years_experience: Optional[FieldValue] = None
    skills: list[FieldValue] = field(default_factory=list)
    experience: list[FieldValue] = field(default_factory=list)
    education: list[FieldValue] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    overall_confidence: float = 0.0
