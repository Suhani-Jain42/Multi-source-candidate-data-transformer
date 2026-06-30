# Multi-Source Candidate Data Transformer

Eightfold Engineering Intern (Jul-Dec 2026) assignment - Step 2 implementation.

## What this is

A pipeline that ingests candidate data from multiple structured and
unstructured sources, normalizes it, merges it into one canonical profile
per candidate (with provenance + confidence), and emits either the default
schema or a custom schema described by a runtime config - same engine, no
code changes.

Pipeline stages: **detect -> extract -> normalize -> merge -> confidence ->
project-to-output -> validate**. See `design_doc/Eightfold_Design.pdf` for
the full reasoning, merge policy, and edge cases (Step 1 deliverable).

## Sources implemented

| Group | Source | File |
|---|---|---|
| Structured | Recruiter CSV export | `src/extractors/csv_extractor.py` |
| Structured | ATS JSON blob (non-matching field names) | `src/extractors/ats_json_extractor.py` |
| Unstructured | Recruiter notes (.txt, free text) | `src/extractors/notes_extractor.py` |
| Unstructured | Resume (PDF / DOCX) | `src/extractors/resume_extractor.py` |
| Unstructured (best-effort) | GitHub profile URL (public REST API) | `src/extractors/github_extractor.py` |

Per the assignment, only one source per group is required - CSV + Resume,
or ATS JSON + Notes, etc. all work. This repo demos all five at once so the
merge/conflict logic has something interesting to do.

## Setup

```bash
cd eightfold
pip install pdfplumber python-docx --break-system-packages   # only needed for resume parsing
```

No other third-party dependencies. (Note: phone normalization is a small
hand-rolled E.164 heuristic, not the `phonenumbers` library - see the design
doc for why, and the known limitation that implies.)

## How to run

**Default schema only:**
```bash
python main.py --inputs sample_inputs/recruiter.csv sample_inputs/ats.json sample_inputs/notes.txt sample_inputs/karthik_resume.pdf --out outputs/result.json
```

**With a custom runtime config (the "required twist"):**
```bash
python main.py --inputs sample_inputs/recruiter.csv sample_inputs/ats.json sample_inputs/notes.txt sample_inputs/karthik_resume.pdf --config sample_inputs/custom_config.json --out outputs/result.json
```

Output JSON has two top-level keys: `default_output` (list of profiles in
the full canonical schema) and `custom_output` (list of profiles reshaped
per your config, or `null` if `--config` wasn't passed).

A run summary (candidates produced, skipped sources, warnings) prints to
stderr so you can see what happened without opening the JSON.

## Sample inputs

No sample inputs were provided with the assignment brief, so
`sample_inputs/` contains synthetic-but-realistic data I authored myself,
deliberately including: a candidate appearing in both the CSV and the notes
file with the same email (merge test), a candidate appearing in both the
CSV and the ATS JSON with a conflicting job title (conflict-resolution
test), a malformed phone number, an empty CSV row, and an empty/garbage
notes block (robustness tests).

## Tests

```bash
pip install pytest --break-system-packages   # if not already available
pytest tests/ -v
```

16 tests, covering: normalization edge cases (phone with/without country
code, malformed email, unparseable dates), pipeline robustness (missing
file, malformed JSON, empty file - none of these should crash), cross-source
merging by email, conflict resolution by source reliability, and the
projection layer's field selection / rename / `on_missing` policies
(`null` / `omit` / `error`).

Run without pytest installed (manual runner, works on this sandbox):
```bash
python3 -c "
import tests.test_pipeline as t, inspect
for n, f in inspect.getmembers(t, inspect.isfunction):
    if n.startswith('test_'):
        f(); print('PASS', n)
"
```

## Known limitations / explicitly descoped (see design doc for full list)

- Phone normalization is a heuristic (no external phone-number library was
  installable offline); defaults to +91 when no country code is present.
- Name-only matching (no email) is the weakest merge key and can cause
  false-positive or false-negative merges on common names - flagged, not
  solved, given time constraints.
- Free-text skill/experience extraction from notes/resumes uses
  deterministic regex heuristics, not an NLP/LLM model, so recall on very
  irregular phrasing is limited (explainability was prioritized over recall).
- GitHub extraction requires outbound network access; if unavailable it
  degrades to zero records with a logged warning rather than crashing.

## Demo video

See submission - covers a default-schema run, a custom-config run, and a
walkthrough of the email-based merge + conflict-resolution edge case.
