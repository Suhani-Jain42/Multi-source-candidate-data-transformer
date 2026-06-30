"""
Stage 1: detect.

Given a file path (or URL string), decide which extractor should handle it.
Detection is based on extension + a light content sniff, never on filename
conventions alone, so misnamed files still degrade gracefully (robustness
constraint) instead of crashing.
"""
from __future__ import annotations
import json
import os


def detect_source_type(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        if "github.com" in path:
            return "github"
        if "linkedin.com" in path:
            return "linkedin"
        return "unknown_url"

    if not os.path.exists(path):
        return "missing"

    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return "recruiter_csv"
    if ext == ".json":
        # Could still be malformed; extractor will validate. Sniff for ATS-ish shape.
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and ("candidate" in data or "ats" in str(data).lower()):
                return "ats_json"
            return "ats_json"
        except Exception:
            return "malformed_json"
    if ext == ".txt":
        return "notes"
    if ext in (".pdf", ".docx"):
        return "resume"
    return "unknown"
