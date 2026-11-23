# Status

Owner: Aktan

State: runs through obkit 0.5.1. The public set is `data/sample.jsonl` (4 companies). The board ranks on the latest funding stage, as the live board does; amount and date are graded in `harness.run grade` reports only. Paid runs are off: `budget_usd` is 0 and no setup has `pricing.answer_usd` yet.

Next step: name the validation and private sets with `obkit add-set`, once the held-out set for v2 is chosen.

Open decisions:
- Raise `budget_usd` above 0 and source `answer_usd` (Fenil).
- The public set has 4 companies. The obkit contract asks for at least 10. Adding questions changes the public set, so it needs a decision.
- Scoring amount and date on the board changes the published number (Fenil).
- A question whose ground truth names no stage has no verdict, which obkit records as a judge error. Leave such questions out of a set; ground truth fixes go into the set itself.
- Cost of failed calls: a vendor error row records 0 cost. Spend on those calls is not counted.
