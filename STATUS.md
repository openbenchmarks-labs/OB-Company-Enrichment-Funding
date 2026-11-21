# Status

Owner: Aktan

State: obkit 0.2.0 adoption is in PR review. The public set is `data/sample.jsonl` (4 companies). Paid runs are off: `budget_usd` is 0 and `answer_usd` is not set.

Next step: a person writes `versions/key-audit.json` for the public set, then `obkit lock` runs and the first dry-run board can be checked.

Open decisions:
- Raise `budget_usd` above 0 and source `answer_usd` (Fenil).
- The public set has 4 companies. The obkit contract asks for at least 10. Adding questions changes the public set, so it needs a decision.
- The board in this repo counts a company as a pass on latest stage alone, per the README. The grader here passes a company only when stage, amount and date are all correct. Pick one before the first paid run.
- A row whose ground truth cannot be scored raises in `judge/obkit.py`, which counts as `judge_error`. The repo board excludes such rows instead.
- Cost of failed calls: a vendor error row records 0 cost. Spend on those calls is not counted.
