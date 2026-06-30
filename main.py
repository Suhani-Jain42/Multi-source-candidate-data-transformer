#!/usr/bin/env python3
"""
Multi-Source Candidate Data Transformer - CLI.

Usage:
    python main.py --inputs sample_inputs/recruiter.csv sample_inputs/ats.json sample_inputs/notes.txt \
                    [--config sample_inputs/custom_config.json] \
                    [--out outputs/result.json]

If --config is omitted, only the default-schema output is produced.
Always prints a short summary (candidates found, warnings, skipped sources)
to stderr/stdout so the demo is easy to narrate.
"""
from __future__ import annotations
import argparse
import json
import sys
from src.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--inputs", nargs="+", required=True, help="Paths/URLs to source files")
    parser.add_argument("--config", help="Path to a runtime output config JSON")
    parser.add_argument("--out", default="outputs/result.json", help="Where to write the JSON output")
    args = parser.parse_args()

    config = None
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    result = run_pipeline(args.inputs, config=config)

    payload = {
        "default_output": result["default_output"],
        "custom_output": result["custom_output"],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Candidates produced: {len(result['default_output'])}", file=sys.stderr)
    print(f"Sources skipped: {len(result['skipped_sources'])}", file=sys.stderr)
    for s in result["skipped_sources"]:
        print(f"  - {s['path']}: {s['reason']}", file=sys.stderr)
    print(f"Warnings: {len(result['warnings'])}", file=sys.stderr)
    for w in result["warnings"][:20]:
        print(f"  - {w}", file=sys.stderr)
    print(f"Output written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
