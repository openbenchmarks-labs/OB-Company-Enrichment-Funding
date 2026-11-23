"""obkit's grade hook: the board ranks on the latest funding stage, as the live board does. The verdict is True, False, or
None when the grader says the ground truth names no stage. Amount and date are graded by `harness.run` reports, not
on the board."""
from __future__ import annotations

import json
from typing import Any

from .grader import grade_stage

VERDICT = {"correct": True, "wrong": False, "not_scoreable": None}


def grade(question: dict[str, Any], answer: str) -> dict[str, bool | None]:
    return {"stage": VERDICT[grade_stage(question["latest_stage"], json.loads(answer).get("latest_stage"))]}
