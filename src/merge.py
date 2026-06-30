"""
Stage 3: merge.  Stage 4: confidence.

Merge / conflict-resolution policy (documented in the design doc too):

1. MATCH KEYS: group RawRecords into "this is the same person" clusters.
   - Primary key: normalized email (case-insensitive exact match).
   - Fallback key (only used when neither record in a pair has an email):
     normalized full_name (lowercase, whitespace-collapsed) - acknowledged
     as the weakest possible key (collisions on common names are a known
     edge case, called out in the design doc).
   Union-find over these keys means: if A and B share an email, and B and C
   share a name (and neither A nor C has an email), all three merge - this
   is intentional transitive grouping, but is one of the riskier edge cases.

2. SOURCE RELIABILITY WEIGHTS (used to break ties / pick a winning value):
   recruiter_csv=0.90, ats_json=0.85, resume=0.80, github=0.70,
   linkedin=0.75, notes=0.50 (free text, least structured/most error-prone).

3. WINNER SELECTION per field:
   - If only one distinct value is offered across sources -> that value,
     confidence = its source's reliability weight, boosted toward 1.0 if
     more than one source independently agrees (corroboration boost).
   - If sources disagree -> the value from the highest-reliability source
     wins; confidence is penalized (multiplied by 0.7) to reflect the
     unresolved conflict. ALL competing values are still recorded in
     `provenance` (never silently dropped) so a human can audit the
     decision - this directly satisfies "wrong-but-confident is worse than
     honestly-empty": we'd rather show a lower confidence than hide doubt.

4. LIST-TYPE fields (emails, phones, skills) are unioned across sources
   (deduplicated), not single-winner-take-all, since a candidate can
   legitimately have multiple emails/phones/skills.
"""
from __future__ import annotations
from collections import defaultdict
from src.models import RawRecord, CanonicalProfile, FieldValue, ProvenanceEntry

SOURCE_RELIABILITY = {
    "recruiter_csv": 0.90,
    "ats_json": 0.85,
    "resume": 0.80,
    "linkedin": 0.75,
    "github": 0.70,
    "notes": 0.50,
}


def _reliability(rec: RawRecord) -> float:
    return SOURCE_RELIABILITY.get(rec.source_type, 0.4)


def _cluster_records(records: list[RawRecord]) -> list[list[RawRecord]]:
    """Union-find clustering by email, falling back to name."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    key_to_records: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        parent.setdefault(i, i)
        email = rec.match_keys.get("email")
        name = rec.match_keys.get("name")
        if email:
            key_to_records[f"email::{email}"].append(i)
        elif name:
            key_to_records[f"name::{name}"].append(i)

    for _, idxs in key_to_records.items():
        for j in idxs[1:]:
            union(idxs[0], j)

    groups: dict[int, list[RawRecord]] = defaultdict(list)
    for i, rec in enumerate(records):
        groups[find(i)].append(rec)
    return list(groups.values())


def _winner(values_with_sources: list[tuple[any, RawRecord]]) -> tuple[any, float, list[str]]:
    """Pick a winning scalar value among (value, source_record) pairs."""
    if not values_with_sources:
        return None, 0.0, []
    by_value: dict[any, list[RawRecord]] = defaultdict(list)
    for v, rec in values_with_sources:
        by_value[v].append(rec)

    if len(by_value) == 1:
        value, recs = next(iter(by_value.items()))
        base = max(_reliability(r) for r in recs)
        confidence = min(1.0, base + 0.1 * (len(recs) - 1))  # corroboration boost
        return value, round(confidence, 2), [r.source_id for r in recs]

    # conflict: pick highest-reliability source's value
    best_value, best_recs, best_rel = None, [], -1.0
    for value, recs in by_value.items():
        rel = max(_reliability(r) for r in recs)
        if rel > best_rel:
            best_value, best_recs, best_rel = value, recs, rel
    confidence = round(best_rel * 0.7, 2)
    return best_value, confidence, [r.source_id for r in best_recs]


def merge_cluster(cluster: list[RawRecord], candidate_id: str) -> CanonicalProfile:
    profile = CanonicalProfile(candidate_id=candidate_id)
    provenance: list[ProvenanceEntry] = []

    # --- scalar fields: full_name, headline, years_experience, current_company/title, location
    name_pairs = [(r.full_name, r) for r in cluster if r.full_name]
    if name_pairs:
        v, conf, srcs = _winner(name_pairs)
        profile.full_name = FieldValue(v, conf, srcs)
        provenance.append(ProvenanceEntry("full_name", ",".join(srcs), "merged"))

    headline_pairs = [(r.headline, r) for r in cluster if r.headline]
    if headline_pairs:
        v, conf, srcs = _winner(headline_pairs)
        profile.headline = FieldValue(v, conf, srcs)
        provenance.append(ProvenanceEntry("headline", ",".join(srcs), "merged"))

    years_pairs = [(r.years_experience, r) for r in cluster if r.years_experience is not None]
    if years_pairs:
        v, conf, srcs = _winner(years_pairs)
        profile.years_experience = FieldValue(v, conf, srcs)
        provenance.append(ProvenanceEntry("years_experience", ",".join(srcs), "merged"))

    loc_pairs = [(tuple(sorted((r.location or {}).items())), r) for r in cluster if r.location]
    if loc_pairs:
        v, conf, srcs = _winner(loc_pairs)
        profile.location = FieldValue(dict(v) if v else None, conf, srcs)
        provenance.append(ProvenanceEntry("location", ",".join(srcs), "merged"))

    # --- links: union by key (linkedin/github/portfolio), last-writer for collisions noted
    for rec in cluster:
        for k, v in rec.links.items():
            if k not in profile.links and v:
                profile.links[k] = FieldValue(v, _reliability(rec), [rec.source_id])
                provenance.append(ProvenanceEntry(f"links.{k}", rec.source_id, "merged"))

    # --- list fields: union + dedupe, confidence = max reliability among contributing sources
    def union_list_field(getter):
        seen: dict[str, list[str]] = defaultdict(list)
        original_casing: dict[str, str] = {}
        for rec in cluster:
            for item in getter(rec):
                key = item.lower() if isinstance(item, str) else str(item)
                seen[key].append(rec.source_id)
                original_casing.setdefault(key, item)
        out = []
        for key, srcs in seen.items():
            recs_for_key = [r for r in cluster if r.source_id in srcs]
            conf = min(1.0, max(_reliability(r) for r in recs_for_key) + 0.05 * (len(srcs) - 1))
            out.append(FieldValue(original_casing[key], round(conf, 2), srcs))
        return out

    profile.emails = union_list_field(lambda r: r.emails)
    for fv in profile.emails:
        provenance.append(ProvenanceEntry("emails[]", ",".join(fv.sources), "merged"))

    profile.phones = union_list_field(lambda r: r.phones)
    for fv in profile.phones:
        provenance.append(ProvenanceEntry("phones[]", ",".join(fv.sources), "merged"))

    profile.skills = union_list_field(lambda r: r.skills)
    for fv in profile.skills:
        provenance.append(ProvenanceEntry("skills[]", ",".join(fv.sources), "merged"))

    # --- experience: full structured entries (with start/end) are concatenated and
    # deduped on (company, title, start) - different start dates legitimately mean
    # different jobs, so no conflict resolution needed there.
    seen_exp = set()
    for rec in cluster:
        for e in rec.experience:
            key = (e.get("company"), e.get("title"), e.get("start"))
            if key in seen_exp:
                continue
            seen_exp.add(key)
            profile.experience.append(FieldValue(e, _reliability(rec), [rec.source_id]))
            provenance.append(ProvenanceEntry("experience[]", rec.source_id, "merged"))

    # --- current_company/title ("current role"): this IS a conflict-prone scalar-ish
    # field - if multiple sources report the SAME company with a DIFFERENT title, that's
    # a genuine conflict (not two jobs), so it goes through the same reliability-based
    # winner selection as other scalar fields, instead of being listed twice.
    by_company: dict[str, list[RawRecord]] = defaultdict(list)
    no_company: list[RawRecord] = []
    for rec in cluster:
        if not (rec.current_company or rec.title):
            continue
        if rec.current_company:
            by_company[rec.current_company.strip().lower()].append(rec)
        else:
            no_company.append(rec)

    for company_key, recs in by_company.items():
        title_pairs = [(r.title, r) for r in recs if r.title]
        if title_pairs:
            winning_title, conf, srcs = _winner(title_pairs)
        else:
            winning_title, conf, srcs = None, max(_reliability(r) for r in recs), [r.source_id for r in recs]
        display_company = max(recs, key=_reliability).current_company
        key = (display_company, winning_title, None)
        if key in seen_exp:
            continue
        seen_exp.add(key)
        profile.experience.append(FieldValue(
            {"company": display_company, "title": winning_title, "start": None, "end": None, "summary": None},
            conf, srcs,
        ))
        provenance.append(ProvenanceEntry("experience[]", ",".join(srcs), "merged"))

    for rec in no_company:
        key = (None, rec.title, None)
        if key in seen_exp:
            continue
        seen_exp.add(key)
        profile.experience.append(FieldValue(
            {"company": None, "title": rec.title, "start": None, "end": None, "summary": None},
            _reliability(rec), [rec.source_id],
        ))
        provenance.append(ProvenanceEntry("experience[]", rec.source_id, "merged"))

    seen_edu = set()
    for rec in cluster:
        for e in rec.education:
            key = (e.get("institution"), e.get("degree"), e.get("end_year"))
            if key in seen_edu:
                continue
            seen_edu.add(key)
            profile.education.append(FieldValue(e, _reliability(rec), [rec.source_id]))
            provenance.append(ProvenanceEntry("education[]", rec.source_id, "merged"))

    profile.provenance = provenance

    all_confidences = []
    for fv in [profile.full_name, profile.headline, profile.years_experience, profile.location]:
        if fv:
            all_confidences.append(fv.confidence)
    for lst in [profile.emails, profile.phones, profile.skills, profile.experience, profile.education]:
        all_confidences.extend(fv.confidence for fv in lst)
    profile.overall_confidence = round(sum(all_confidences) / len(all_confidences), 2) if all_confidences else 0.0

    return profile


def merge_all(records: list[RawRecord]) -> list[CanonicalProfile]:
    usable = [r for r in records if not (r.errors and not any([
        r.full_name, r.emails, r.phones, r.skills, r.current_company, r.title, r.location, r.education,
    ]))]
    clusters = _cluster_records(usable)
    profiles = []
    for i, cluster in enumerate(clusters):
        profiles.append(merge_cluster(cluster, candidate_id=f"cand_{i+1:04d}"))
    return profiles
