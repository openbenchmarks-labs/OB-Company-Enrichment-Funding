"""obkit's grade hook: the repo's own field grader. Each graded field is one verdict: True, False, or None when the grader
says the ground truth cannot be scored for it."""
from __future__ import annotations

import json
from typing import Any

from harness.models import FIELDS

from .grader import grade_row

VERDICT = {"correct": True, "wrong": False, "not_scoreable": None}
NAMES = {"stage": "latest_stage", "amount": "amount", "date": "announced_on"}


def grade(question: dict[str, Any], answer: str) -> dict[str, bool | None]:
    verdicts = grade_row({f: question[f] for f in FIELDS}, json.loads(answer))
    return {name: VERDICT[verdicts[field]] for name, field in NAMES.items()}
