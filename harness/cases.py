"""Read the companies file: the repo's CSV, or a Hugging Face dataset file (JSONL) as published."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

# Hugging Face column -> the CSV column the runners and the judge read.
HF_COLUMNS = {
    "case_id": "candidate_id",
    "input_name": "company_name",
    "input_domain": "company_domain",
    "latest_stage": "answer_stage",
    "latest_announced_on": "answer_announced_on",
    "latest_amount": "answer_amount",
    "currency": "answer_currency",
}
INPUTS = ("case_id", "input_name", "input_domain")


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_cases(text: str) -> list[dict[str, str]]:
    """Rows as the CSV gives them. A file whose first character is `{` is read as Hugging Face JSONL."""
    if not text.lstrip().startswith("{"):
        return list(csv.DictReader(io.StringIO(text, newline="")))
    rows = []
    for line in text.splitlines():
        if line.strip():
            row = json.loads(line)
            missing = [name for name in INPUTS if not row.get(name)]
            if missing:
                raise ValueError(f"Hugging Face row has no {', '.join(missing)}: {line[:120]}")
            rows.append({csv_name: _cell(row.get(hf_name)) for hf_name, csv_name in HF_COLUMNS.items()})
    return rows


def read_cases(path: Path) -> list[dict[str, str]]:
    return parse_cases(path.read_text(encoding="utf-8-sig"))
