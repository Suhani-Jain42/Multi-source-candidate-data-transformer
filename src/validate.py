"""
Stage 6: validate.

Validates a PROJECTED output dict against the config that produced it
(type-checks each requested field; flags required-but-null fields under
"error" missing-policy; never raises on degraded-but-valid output).
Validating the default (un-projected) output is a simple type pass too.
"""
from __future__ import annotations

TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str) or v is None,
    "string[]": lambda v: v is None or (isinstance(v, list) and all(isinstance(x, str) for x in v)),
    "number": lambda v: v is None or isinstance(v, (int, float)),
    "boolean": lambda v: v is None or isinstance(v, bool),
}


def validate_projection(result: dict, config: dict) -> list[str]:
    """Returns a list of human-readable validation problems (empty = valid)."""
    problems = []
    on_missing = config.get("on_missing", "null")
    for field_cfg in config.get("fields", []):
        path = field_cfg["path"]
        expected_type = field_cfg.get("type")
        required = field_cfg.get("required", False)
        if path not in result:
            if required and on_missing != "omit":
                problems.append(f"required field '{path}' missing from projected output")
            continue
        value = result[path]
        if value is None:
            if required and on_missing == "error":
                problems.append(f"required field '{path}' is null under on_missing=error policy")
            continue
        if expected_type and expected_type in TYPE_CHECKS and not TYPE_CHECKS[expected_type](value):
            problems.append(f"field '{path}' expected type {expected_type}, got {type(value).__name__}")
    return problems


def validate_default_output(output: dict) -> list[str]:
    problems = []
    if not output.get("candidate_id"):
        problems.append("candidate_id missing")
    if not isinstance(output.get("emails", []), list):
        problems.append("emails must be a list")
    if not isinstance(output.get("phones", []), list):
        problems.append("phones must be a list")
    conf = output.get("overall_confidence")
    if conf is not None and not (0.0 <= conf <= 1.0):
        problems.append(f"overall_confidence out of [0,1] range: {conf}")
    return problems
