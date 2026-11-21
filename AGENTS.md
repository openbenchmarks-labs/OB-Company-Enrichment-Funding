# Commands

Run from the repo root with the venv that `requirements.txt` and obkit 0.2.0 install into.

- `.venv/bin/obkit check`: validate the benchmark layout, hooks and selftest. Prints `check: ok` when clean.
- `.venv/bin/obkit lock --reason "<why>"`: freeze the benchmark version. Needs `versions/key-audit.json` for the public set.
- `.venv/bin/obkit run --set public --tools <setup> --dry`: run one setup with canned replies, no network, no spend.
- `.venv/bin/obkit judge runs/<run id>`: grade a run and print the board lines.
