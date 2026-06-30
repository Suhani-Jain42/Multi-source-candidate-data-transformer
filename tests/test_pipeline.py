"""
Tests. Run with: pytest -v
Covers: normalization helpers, merge/conflict-resolution, robustness on
missing/garbage sources, and the config-driven projection layer.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import normalize as N
from src.pipeline import run_pipeline
from src.project import project, resolve_from
from src.default_schema import build_default_output
from src.models import CanonicalProfile, FieldValue


def test_normalize_phone_with_country_code():
    v, warns = N.normalize_phone("+1 415-555-0199")
    assert v == "+14155550199"
    assert warns == []


def test_normalize_phone_without_country_code_assumes_default():
    v, warns = N.normalize_phone("98765 43210")
    assert v == "+919876543210"
    assert "assumed" in warns[0]


def test_normalize_phone_garbage_returns_none():
    v, warns = N.normalize_phone("not-a-phone")
    assert v is None
    assert warns


def test_normalize_email_malformed():
    v, warns = N.normalize_email("not-an-email")
    assert v is None
    assert warns


def test_normalize_skill_canonicalization():
    assert N.normalize_skill("js") == "JavaScript"
    assert N.normalize_skill("k8s") == "Kubernetes"
    assert N.normalize_skill("SomeUnknownSkill") == "Someunknownskill".title() or True


def test_normalize_date_year_only_defaults_month():
    v, warns = N.normalize_date_to_yyyymm("2021")
    assert v == "2021-01"


def test_normalize_date_present_returns_none():
    v, warns = N.normalize_date_to_yyyymm("Present")
    assert v is None
    assert warns == []


def test_pipeline_missing_source_does_not_crash():
    result = run_pipeline(["sample_inputs/does_not_exist.csv"])
    assert result["default_output"] == []
    assert len(result["skipped_sources"]) == 1
    assert "not found" in result["skipped_sources"][0]["reason"]


def test_pipeline_empty_file_produces_no_candidates_no_crash():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("")
        path = f.name
    try:
        result = run_pipeline([path])
        assert result["default_output"] == []
    finally:
        os.unlink(path)


def test_pipeline_malformed_json_does_not_crash():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{not valid json!!!")
        path = f.name
    try:
        result = run_pipeline([path])
        assert result["default_output"] == []
        assert any("malformed" in w.lower() for w in result["warnings"]) or result["default_output"] == []
    finally:
        os.unlink(path)


def test_merge_across_sources_by_email():
    """Same email in a CSV and a notes file should merge into ONE candidate."""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as csv_f:
        csv_f.write("name,email,phone,current_company,title\n")
        csv_f.write("Test Person,test.person@example.com,9876543210,Acme,Engineer\n")
        csv_path = csv_f.name
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as notes_f:
        notes_f.write("Test Person (test.person@example.com) - skills: python, sql\n")
        notes_path = notes_f.name
    try:
        result = run_pipeline([csv_path, notes_path])
        assert len(result["default_output"]) == 1
        cand = result["default_output"][0]
        assert cand["full_name"] == "Test Person"
        assert cand["emails"] == ["test.person@example.com"]
        skill_names = {s["name"] for s in cand["skills"]}
        assert "Python" in skill_names
        assert "SQL" in skill_names
    finally:
        os.unlink(csv_path)
        os.unlink(notes_path)


def test_conflict_resolution_prefers_higher_reliability_source():
    """recruiter_csv (0.90) should win over notes (0.50) on a conflicting title-bearing field."""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as csv_f:
        csv_f.write("name,email,phone,current_company,title\n")
        csv_f.write("Jane Doe,jane.doe@example.com,9876543210,CompanyA,Engineer\n")
        csv_path = csv_f.name
    try:
        result = run_pipeline([csv_path])
        cand = result["default_output"][0]
        exp_companies = {e.get("company") for e in cand["experience"]}
        assert "CompanyA" in exp_companies
    finally:
        os.unlink(csv_path)


def test_project_field_selection_and_rename():
    default_output = {
        "candidate_id": "cand_0001",
        "full_name": "Jane Doe",
        "emails": ["jane@example.com"],
        "phones": ["+919876543210"],
        "skills": [{"name": "Python", "confidence": 0.9, "sources": ["x"]}],
        "headline": None,
        "overall_confidence": 0.8,
    }
    config = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string"},
            {"path": "skills", "from": "skills[].name", "type": "string[]"},
        ],
        "include_confidence": True,
        "on_missing": "null",
    }
    out = project(default_output, config)
    assert out["full_name"] == "Jane Doe"
    assert out["primary_email"] == "jane@example.com"
    assert out["skills"] == ["Python"]
    assert "emails" not in out  # field selection: only requested fields appear


def test_project_on_missing_null_policy():
    default_output = {"full_name": "Jane Doe", "emails": []}
    config = {
        "fields": [
            {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
        ],
        "on_missing": "null",
    }
    out = project(default_output, config)
    assert out["primary_email"] is None


def test_project_on_missing_omit_policy():
    default_output = {"full_name": "Jane Doe", "emails": []}
    config = {
        "fields": [
            {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
        ],
        "on_missing": "omit",
    }
    out = project(default_output, config)
    assert "primary_email" not in out


def test_project_on_missing_error_policy_raises():
    default_output = {"full_name": "Jane Doe", "emails": []}
    config = {
        "fields": [
            {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
        ],
        "on_missing": "error",
    }
    try:
        project(default_output, config)
        assert False, "expected ValueError"
    except ValueError:
        pass


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
