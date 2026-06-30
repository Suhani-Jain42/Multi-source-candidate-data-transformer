"""
Orchestrator: detect -> extract -> normalize -> merge -> confidence ->
project-to-output -> validate.

`confidence` is computed inline during merge (see merge.py docstring) rather
than as a fully separate pass, since confidence is a property of *how a
field got merged*, not a thing you can sensibly bolt on afterward without
re-deriving the same source-agreement info merge already computed.
"""
from __future__ import annotations
import json
from src.detect import detect_source_type
from src.extractors import csv_extractor, ats_json_extractor, notes_extractor, resume_extractor, github_extractor
from src.normalize_record import normalize_record
from src.merge import merge_all
from src.default_schema import build_default_output
from src.project import project
from src.validate import validate_projection, validate_default_output

EXTRACTOR_BY_TYPE = {
    "recruiter_csv": csv_extractor.extract,
    "ats_json": ats_json_extractor.extract,
    "notes": notes_extractor.extract,
    "resume": resume_extractor.extract,
    "github": github_extractor.extract,
}


def run_pipeline(input_paths: list[str], config: dict | None = None) -> dict:
    """
    Run the full pipeline over a list of source paths/URLs.
    Returns {"default_output": [...], "custom_output": [...] or None,
             "warnings": [...], "skipped_sources": [...]}
    """
    all_records = []
    warnings = []
    skipped = []

    for path in input_paths:
        source_type = detect_source_type(path)
        if source_type in ("missing",):
            skipped.append({"path": path, "reason": "file not found"})
            continue
        if source_type in ("malformed_json", "unknown", "unknown_url"):
            skipped.append({"path": path, "reason": f"unrecognized/malformed source ({source_type})"})
            continue
        extractor = EXTRACTOR_BY_TYPE.get(source_type)
        if extractor is None:
            skipped.append({"path": path, "reason": f"no extractor registered for type {source_type}"})
            continue
        try:
            records = extractor(path)
        except Exception as e:
            # Constraint: a missing/garbage source must never crash the run.
            skipped.append({"path": path, "reason": f"extractor raised unexpected error: {e}"})
            continue

        for rec in records:
            rec = normalize_record(rec)
            if rec.errors:
                warnings.extend(f"[{rec.source_id}] {w}" for w in rec.errors)
            all_records.append(rec)

    profiles = merge_all(all_records)
    default_outputs = [build_default_output(p) for p in profiles]

    for out in default_outputs:
        problems = validate_default_output(out)
        if problems:
            warnings.extend(f"[{out['candidate_id']}] default schema: {p}" for p in problems)

    custom_outputs = None
    if config:
        custom_outputs = []
        for out in default_outputs:
            try:
                projected = project(out, config)
                problems = validate_projection(projected, config)
                if problems:
                    warnings.extend(f"[{out['candidate_id']}] custom schema: {p}" for p in problems)
                custom_outputs.append(projected)
            except ValueError as e:
                warnings.append(f"[{out['candidate_id']}] projection failed: {e}")
                custom_outputs.append(None)

    return {
        "default_output": default_outputs,
        "custom_output": custom_outputs,
        "warnings": warnings,
        "skipped_sources": skipped,
    }
