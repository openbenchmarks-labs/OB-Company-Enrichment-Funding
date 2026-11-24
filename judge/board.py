"""Build the board from saved judgments: stage correct over every company in the cohort.

Every company counts in the denominator (a blank answer-key stage passes every
answer, rule 6 of the judge prompt). A company is correct when the judge says so.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JUDGMENTS = ROOT / "runs" / "judgments"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judgments-dir", type=Path, default=DEFAULT_JUDGMENTS)
    args = parser.parse_args()
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"eligible": 0, "correct": 0})
    seen: set[tuple[str, str]] = set()
    for path in sorted(args.judgments_dir.glob("*.json")):
        row = json.loads(path.read_text())
        provider = row["provider"]
        for judgment in row["judgments"]:
            key = (provider, judgment["record_id"])
            if key in seen:
                raise RuntimeError(f"duplicate judgment for {key}")
            seen.add(key)
            totals[provider]["eligible"] += 1
            totals[provider]["correct"] += 1 if judgment["correct"] else 0
    board = sorted(
        ({"provider": provider, "eligible_stage_cases": value["eligible"], "correct_stage_count": value["correct"],
          "stage_correct_yield_pct": round(100 * value["correct"] / value["eligible"], 2)}
         for provider, value in totals.items()),
        key=lambda row: -row["stage_correct_yield_pct"],
    )
    print(json.dumps(board, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
