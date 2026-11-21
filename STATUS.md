# Status

Owner: Aktan

State: obkit 0.3.0 adoption is in PR review. The public set is `data/sample.jsonl` (4 companies). Each company is scored per field (stage, amount, date); the board unit is fields. Paid runs are off: `budget_usd` is 0 and `answer_usd` is not set.

Next step: a person writes `versions/key-audit.json` for the public set, then `obkit lock` runs and the first dry-run board can be checked.

Open decisions:
- Raise `budget_usd` above 0 and source `answer_usd` (Fenil).
- The public set has 4 companies. The obkit contract asks for at least 10. Adding questions changes the public set, so it needs a decision.
- Board unit: the board scores fields. The README's stage-only board is not this board; the README is not changed here.
- A field whose ground truth cannot be scored returns None in `judge/obkit.py` and is left out of the board.
- Cost of failed calls: a vendor error row records 0 cost. Spend on those calls is not counted.
