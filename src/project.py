"""
Stage 5: project-to-output (the "required twist").

Takes the DEFAULT output dict (default_schema.py) plus a runtime config and
reshapes it - same engine, no code changes - per the config's:
  - field subset / selection
  - rename/remap via "from" (a path into the default dict)
  - per-field "normalize" (re-applied here so a custom config can ask for a
    different shape than the default already has, e.g. picking emails[0]
    out of a list and re-normalizing it)
  - include_confidence / include_provenance toggles
  - on_missing policy: "null" | "omit" | "error"

Path syntax supported in "from":
  "a.b"          -> dict.get   chain
  "a[0]"         -> index into list
  "a[].b"        -> map: extract .b from every item in list a (list of dicts)
"""
from __future__ import annotations
import re
from src import normalize as N

PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)(\[\])?(\[(\d+)\])?")


def _resolve_path(data: dict, path: str):
    """Resolve a dotted/bracket path against `data`. Returns (value, found: bool)."""
    current = data
    for raw_token in path.split("."):
        m = PATH_TOKEN_RE.fullmatch(raw_token)
        if not m:
            return None, False
        key, is_map, _, idx = m.groups()
        if not isinstance(current, dict) or key not in current:
            return None, False
        current = current[key]
        if is_map:
            if not isinstance(current, list):
                return None, False
            # remaining path (after this token) describes the sub-field to map over;
            # caller (resolve_from) handles the suffix - here we just return the raw list
            return current, True
        if idx is not None:
            i = int(idx)
            if not isinstance(current, list) or i >= len(current):
                return None, False
            current = current[i]
    return current, True


def resolve_from(data: dict, from_path: str):
    """
    Resolves a "from" path that may contain a "[].subfield" mapping segment,
    e.g. "skills[].name" -> [s["name"] for s in data["skills"]]
    """
    if "[]." in from_path:
        list_path, subfield = from_path.split("[].", 1)
        lst, found = _resolve_path(data, list_path)
        if not found or not isinstance(lst, list):
            return None, False
        out = []
        for item in lst:
            if isinstance(item, dict) and subfield in item:
                out.append(item[subfield])
        return out, True
    return _resolve_path(data, from_path)


def _apply_normalize(value, normalize_kind: str):
    if value is None:
        return value
    if normalize_kind in ("E164", "e164"):
        if isinstance(value, list):
            out = []
            for v in value:
                nv, _ = N.normalize_phone(v)
                if nv:
                    out.append(nv)
            return out
        nv, _ = N.normalize_phone(value)
        return nv
    if normalize_kind == "canonical":
        if isinstance(value, list):
            return [N.normalize_skill(v) for v in value]
        return N.normalize_skill(value)
    return value


def project(default_output: dict, config: dict) -> dict:
    """Apply a runtime config to the default output. Returns the custom-shaped dict."""
    fields_cfg = config.get("fields", [])
    include_confidence = config.get("include_confidence", True)
    include_provenance = config.get("include_provenance", True)
    on_missing = config.get("on_missing", "null")  # "null" | "omit" | "error"

    result: dict = {}
    missing_required: list[str] = []

    for field_cfg in fields_cfg:
        out_path = field_cfg["path"]
        from_path = field_cfg.get("from", out_path)
        required = field_cfg.get("required", False)
        normalize_kind = field_cfg.get("normalize")

        value, found = resolve_from(default_output, from_path)
        if not found or value is None or value == [] or value == "":
            if required:
                missing_required.append(out_path)
            if on_missing == "omit":
                continue
            elif on_missing == "error" and required:
                continue  # error raised below after collecting all
            result[out_path] = None
            continue

        if normalize_kind:
            value = _apply_normalize(value, normalize_kind)

        result[out_path] = value

    if on_missing == "error" and missing_required:
        raise ValueError(f"Required fields missing after projection: {missing_required}")

    if not include_confidence:
        result.pop("overall_confidence", None)
        if "skills" in result and isinstance(result["skills"], list) and result["skills"] and isinstance(result["skills"][0], dict):
            result["skills"] = [s.get("name") if isinstance(s, dict) else s for s in result["skills"]]
    if not include_provenance:
        result.pop("provenance", None)

    return result
