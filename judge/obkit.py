"""obkit's grade hook: the repo's own field grader. An answer passes when all three graded fields are correct."""
from __future__ import annotations

import json
from typing import Any

from harness.models import FIELDS

from .grader import grade_row


def grade(question: dict[str, Any], answer: str) -> bool:
    verdicts = grade_row({f: question[f] for f in FIELDS}, json.loads(answer))
    if "not_scoreable" in verdicts.values():
        # The repo's board excludes such a row; obkit has no exclusion, so it is an error to count against judge_error_max.
        raise ValueError(f"ground truth cannot be scored: {verdicts}")
    return all(v == "correct" for v in verdicts.values())
