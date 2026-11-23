# AGENTS.md — OB-Company-Funding

Quick navigation guide for coding agents working in `OB-Company-Funding`.

## Structure (Zero Overlap)

| Folder | Owns | Files |
|---|---|---|
| **`data/`** | Dataset schema & public sample rows | `data/README.md`, `data/sample.jsonl` |
| **`harness/`** | Execution only: CLI runner, tool registry, tool adapters, HTTP client | `harness/run.py`, `harness/runner.py`, `harness/registry.py`, `harness/adapters/<tool>.py`, `harness/question.py`, `harness/http_client.py`, `harness/llm.py`, `harness/config.yaml` |
| **`tools/`** | Tool setups, request settings & prices (one file per tool for clean PRs) | `tools/<tool>.yaml` (15 tools, 27 setups) |
| **`judge/`** | Deterministic grader, rules, board math, stage aliases | `judge/grader.py`, `judge/config.yaml`, `judge/stage_aliases.json` |

Benchmark order & win condition live at the root in `benchmark.yaml`.

## Commands

```sh
uv venv && uv pip install -r requirements.txt
.venv/bin/python -B -m harness.run selftest --tasks data/sample.jsonl
```

## obkit

The same adapters and grader also run through obkit 0.5.1 (`harness/obkit.py`, `judge/obkit.py`). Install it into the same venv with `uv pip install "obkit @ git+https://github.com/openbenchmarks-labs/obkit@v0.5.1"`.

- `.venv/bin/obkit check`: validate the benchmark layout, hooks and selftest. Prints `check: ok` when clean.
- `.venv/bin/obkit go --set public --tools <setup> --dry`: run one setup with canned replies, no network, no spend, then judge it and print the board.
- `.venv/bin/obkit add-set validation|private FILE`: store a held-out set by its sha256 and name it in `benchmark.yaml`.

## Guidelines

- **Keep folders strictly separated:** Dataset info in `data/`; execution in `harness/`; per-tool configs in `tools/<tool>.yaml`; grading in `judge/`.
- **Adding or tuning a tool:** Create or edit `tools/<tool>.yaml`. A new tool also needs `harness/adapters/<tool>.py`. Then run `selftest`.
- **No secrets or raw run logs in git:** Keep API keys in `.env` and run outputs in `runs/` (both gitignored).
- **Consistent terminology:** Use `tool`, `setup`, `question`, `ground truth`, `board`, `main score`.
