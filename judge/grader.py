"""Deterministic grader for Company Funding: latest_stage, amount (+-5%), announced_on (+-7 days)."""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((HERE / "config.yaml").read_text())
ALIASES = json.loads((HERE / "stage_aliases.json").read_text())

# A Series letter: "Series B", "series_b_plus", "Series B-1 bridge", "B", "B4", "B+", "B轮".
SERIES_RE = re.compile(r"^series ?([a-z])(?![a-z])")
BARE_SERIES_RE = re.compile(r"^([a-z])(?:\d+|\++)?$")
CJK_SERIES_RE = re.compile(r"^([a-z])\d*\+?轮")
HEAD_SPLIT_RE = re.compile(r"\s+[-–]\s+")
ALT_SPLIT_RE = re.compile(r"\s*/\s*|\s+and\s+|\s+or\s+")
PAREN_RE = re.compile(r"\([^)]*\)")
DROP_TOKENS = ("round", "financing")


def _unify_parens(raw: str) -> str:
    return raw.replace("（", "(").replace("）", ")")


def _norm_label(raw: str | None) -> str:
    """stage_aliases.json `normalisation`: lowercase, parentheses and a ' - Company' tail dropped, '_' and '-' read as
    spaces, the words round and financing dropped unless nothing else remains."""
    if raw is None:
        return ""
    s = PAREN_RE.sub(" ", _unify_parens(str(raw)).lower().strip())
    s = HEAD_SPLIT_RE.split(s, maxsplit=1)[0]
    tokens = s.replace("_", " ").replace("-", " ").split()
    kept = [t for t in tokens if t not in DROP_TOKENS]
    return " ".join(kept or tokens)


STAGE_FIELD = CONFIG["judge"]["fields"]["latest_stage"]
ADDITIONS = STAGE_FIELD.get("additions") or {}
RULES = STAGE_FIELD["rules"]

# stage_aliases.json `special.early_stage`: "Early Stage key accepts Seed or Pre-Seed only."
EARLY_STAGE_ACCEPTS = frozenset({"seed_group", "pre_seed"})


def _build_stage_map() -> dict[str, str]:
    """Label -> class. Table aliases, then table group members, then config additions; `same_class` reads each class of a
    group as the group's first."""
    mapping: dict[str, str] = {}
    for alias, name in (ALIASES.get("aliases") or {}).items():
        mapping[_norm_label(alias)] = name
    for group_name, info in (ALIASES.get("groups") or {}).items():
        for member in info.get("members", []):
            mapping[_norm_label(member)] = group_name
    for alias, name in (ADDITIONS.get("aliases") or {}).items():
        mapping[_norm_label(alias)] = name
    return {label: SAME_CLASS.get(name, name) for label, name in mapping.items()}


SAME_CLASS = {name: group[0] for group in ADDITIONS.get("same_class") or [] for name in group}
STAGE_MAP = _build_stage_map()
KEY_ACCEPTS = {
    SAME_CLASS.get(key, key): {SAME_CLASS.get(a, a) for a in answers}
    for key, answers in (ADDITIONS.get("key_accepts") or {}).items()
}


def canonical_stage(raw: str | None) -> str:
    """The class a label names: `series_<letter>`, a table class, or "" when the label is blank or unmapped."""
    norm = _norm_label(raw)
    if not norm:
        return ""
    m = SERIES_RE.match(norm) or BARE_SERIES_RE.match(norm) or CJK_SERIES_RE.match(_unify_parens(str(raw)).lower().strip())
    if m:
        return f"series_{m.group(1)}"
    return STAGE_MAP.get(norm, "")


def _parts(raw: str) -> list[str]:
    """A label naming alternatives ("Series A/B", "Seed and Series A") split into its labels."""
    head = PAREN_RE.sub(" ", HEAD_SPLIT_RE.split(_unify_parens(raw).strip(), maxsplit=1)[0])
    return [p for p in ALT_SPLIT_RE.split(head) if p.strip()] or [raw]


def _answer_stage(raw: str) -> str:
    """The class an answer names; "two" when it names two different stages ("Seed and Series A", "Pre-Seed and Debt")."""
    whole = _norm_label(raw)
    if whole in STAGE_MAP:
        return STAGE_MAP[whole]
    classes = {canonical_stage(p) for p in _parts(raw)} - {"", "nostage"}
    if len(classes) > 1:
        return "two"
    return classes.pop() if classes else canonical_stage(raw)


def grade_stage(truth: str | None, pred: str | None) -> str:
    if truth is None or not str(truth).strip():
        return RULES["blank_key"]
    parts = _parts(str(truth)) if RULES["key_alternatives"] else [str(truth)]
    stages = {canonical_stage(p) for p in parts} - {"", "nostage"}
    if not stages:
        # The key names no stage ("venture_unspecified", "None") or none the table reads: nothing to grade against.
        return RULES["key_no_stage"]
    if stages == {"undisclosed"}:
        return RULES["undisclosed_key"]
    if pred is None or not str(pred).strip():
        return "correct" if "undisclosed" in stages else "wrong"
    p_can = _answer_stage(str(pred))
    if p_can == "two":
        return "wrong"
    if "early_stage" in stages and p_can in EARLY_STAGE_ACCEPTS:
        return "correct"
    if p_can and p_can != "nostage":
        accepted = p_can in stages or any(p_can in KEY_ACCEPTS.get(k, ()) for k in stages)
        return "correct" if accepted else "wrong"
    # An answer that names no stage, or a label no rule reads, is right only as the key's own words.
    return "correct" if _norm_label(pred) in {_norm_label(p) for p in parts} else "wrong"


def grade_amount(
    truth: float | int | None, pred: float | int | None, pct: float = 5.0,
    truth_currency: str | None = None, pred_currency: str | None = None,
) -> str:
    """Within `pct` percent of the key. When both sides name a currency, the answer must be in the key's."""
    if truth is None or truth <= 0:
        return "not_scoreable"
    if pred is None or pred <= 0:
        return "wrong"
    if truth_currency and pred_currency and truth_currency.upper() != pred_currency.upper():
        return "wrong"
    return "correct" if abs(float(pred) - float(truth)) / float(truth) <= (pct / 100.0) else "wrong"


def grade_date(truth: str | None, pred: str | None, days: int = 7) -> str:
    if not truth:
        return "not_scoreable"
    if not pred:
        return "wrong"
    try:
        d_truth = date.fromisoformat(str(truth)[:10])
        d_pred = date.fromisoformat(str(pred)[:10])
    except ValueError:
        return "wrong"
    return "correct" if abs((d_pred - d_truth).days) <= days else "wrong"


def grade_row(truth: dict[str, Any], pred: dict[str, Any]) -> dict[str, str]:
    fields = CONFIG["judge"]["fields"]
    pred_currency = pred.get("currency") or (pred.get("extra") or {}).get("currency")
    return {
        "latest_stage": grade_stage(truth.get("latest_stage"), pred.get("latest_stage")),
        "amount": grade_amount(
            truth.get("amount"), pred.get("amount"), fields["amount"]["percent"], truth.get("currency"), pred_currency
        ),
        "announced_on": grade_date(truth.get("announced_on"), pred.get("announced_on"), days=fields["announced_on"]["days"]),
    }


def wilson95(correct: int, total: int) -> tuple[float, float, float]:
    if total <= 0:
        return (0.0, 0.0, 0.0)
    z = 1.959963984540054
    p = correct / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))
