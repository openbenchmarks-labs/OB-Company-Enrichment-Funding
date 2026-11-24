# AGENTS.md: OB-Company-Funding

| Folder | Owns |
|---|---|
| `data/` | The public sample in the input format (`sample.csv`). |
| `harness/` | Provider calls and runners. One saved JSON file per provider and company under `runs/raw/`. |
| `judge/` | The stage judge (`judge.py`) and the board count (`board.py`). |

## Commands

```sh
uv venv && uv pip install -r requirements.txt
.venv/bin/python -m harness.run_research exa --dry-run
```

## Rules

- This code is the benchmark the board runs. A change to the judge prompt, the instruction, the output schema or a provider request changes published scores: it goes in its own pull request with the reason.
- Keep API keys in `.env` and run outputs in `runs/`. Both are gitignored.
