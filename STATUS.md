# Status

Owner: Aktan

State: runs through obkit 0.5.1. The public set is `data/sample.jsonl` (4 companies). Each company is scored per field (stage, amount, date); the board unit is fields. Paid runs are off: `budget_usd` is 0 and no setup has `pricing.answer_usd` yet.

Next step: name the validation and private sets with `obkit add-set`, once the held-out set for v2 is chosen.

Open decisions:
- Raise `budget_usd` above 0 and source `answer_usd` (Fenil).
- The public set has 4 companies. The obkit contract asks for at least 10. Adding questions changes the public set, so it needs a decision.
- Board unit: the board scores fields. The README's stage-only board is not this board; the README is not changed here.
- A field whose ground truth cannot be scored returns None in `judge/obkit.py` and is left out of the board.
- Cost of failed calls: a vendor error row records 0 cost. Spend on those calls is not counted.
