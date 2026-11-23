# Commands

Run from the repo root with the venv that `requirements.txt` and obkit 0.4.0 install into.

- `.venv/bin/obkit check`: validate the benchmark layout, hooks and selftest. Prints `check: ok` when clean.
- `.venv/bin/obkit go --set public --tools <setup> --dry`: run one setup with canned replies, no network, no spend, then judge it and print the board.
- `.venv/bin/obkit add-set validation|private FILE`: store a held-out set by its sha256 and name it in `benchmark.yaml`.
