"""Judge each provider's latest funding stage against the answer key with GPT-5.6 Terra.

Reads the company CSV (answer key) and the saved run cells under runs/raw, sends
one Responses API call per 50 records, and writes every judgment to runs/judgments.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "sample.csv"
DEFAULT_RAW_DIR = ROOT / "runs" / "raw"
DEFAULT_OUTPUT_DIR = ROOT / "runs" / "judgments"
BATCH_SIZE = 50

PROMPT = """You are a strict evaluator for a company-funding benchmark. Evaluate each record independently.

Use only the supplied values. Do not research companies, infer facts, or use outside knowledge.
Ignore capitalization, underscores, hyphens, extra spaces, and the words \"round\" or \"financing\" when they do not change a funding type.

Rules:
1. Series A through Series H are strict: the vendor must state the same letter. A same-letter suffix does not change the Series: Series B matches B, B1, B2, B3, B+, B Plus, Series B, Series B+, and series_b_plus. A date or amount never rescues a wrong or missing Series letter. Seed, Pre-Seed, Venture, Private Equity, Debt, and unspecified funding rounds do not match a Series letter.
2. The following non-Series labels are equivalent, in either direction:
   - Seed, Seed Bridge, and Pre-Series A.
   - Private Equity, PE, PE Growth, Growth Investment, Growth Equity,
     Strategic Funding, Strategic Round, Strategic Investment, Corporate
     Investment, and Corporate Round.
   - Equity Crowdfunding, Grant, and Non-Equity Assistance.
3. Seed and Pre-Seed are distinct: neither matches the other. The Seed / Pre-Series A equivalence in rule 2 is the only exception involving Pre-Series A.
4. If ground truth is Early Stage, Seed and Pre-Seed vendor stages are correct.
5. If ground truth is Undisclosed, an Undisclosed or null/blank vendor stage is correct.
6. If ground truth stage is null or blank, every vendor answer is correct.
7. For every other non-Series ground-truth stage: accept a clearly equivalent
   stage. If stages are not equivalent, accept only if dates are both present
   and exactly identical, or amounts are both present and exactly numerically
   identical. Amounts are whole major-currency units; never use approximate
   equality.
8. Generic or vague labels (funding, funding round, venture, other, unknown,
   private financing, early-stage, structured financing) are not stage matches
   unless explicitly allowed above.

Return exactly one result for every input record. Copy its record_id exactly. Reasons must be concise and name the rule used.
"""

RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "record_id": {"type": "string"},
                    "scoreable": {"type": "boolean"},
                    "correct": {"type": "boolean"},
                    "decision_basis": {
                        "type": "string",
                        "enum": [
                            "same_series_letter", "equivalent_stage", "exact_date_match",
                            "exact_amount_match", "blank_ground_truth_pass", "incorrect",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["record_id", "scoreable", "correct", "decision_basis", "reason"],
            },
        },
    },
    "required": ["results"],
}


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def record(case: dict[str, str], run: dict[str, Any]) -> dict[str, Any]:
    vendor = run.get("normalized") or {}
    return {
        "record_id": case["candidate_id"],
        "company_name": case["company_name"],
        "company_domain": case["company_domain"],
        "ground_truth": {
            "latest_stage": case["answer_stage"] or None,
            "latest_amount": case["answer_amount"] or None,
            "latest_announced_on": case["answer_announced_on"] or None,
        },
        "vendor": {"run_status": run.get("status"), "latest_stage": vendor.get("latest_stage"), "latest_amount": vendor.get("latest_amount"), "latest_announced_on": vendor.get("latest_announced_on") or vendor.get("latest_date")},
    }


def judge(provider: str, records: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).responses.create(
        model=os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.6-terra"),
        reasoning={"effort": os.getenv("OPENAI_JUDGE_REASONING_EFFORT", "medium")},
        text={"verbosity": "low", "format": {"type": "json_schema", "name": "funding_stage_judgments", "strict": True, "schema": RESULT_SCHEMA}},
        max_output_tokens=12_000,
        input=[{"role": "developer", "content": PROMPT}, {"role": "user", "content": json.dumps({"records": records}, separators=(",", ":"))}],
    )
    payload = json.loads(response.output_text)
    judgments = payload["results"]
    expected = {row["record_id"] for row in records}
    if {row["record_id"] for row in judgments} != expected or len(judgments) != len(records):
        raise RuntimeError(f"{provider}: response records do not exactly match request")
    result = {"provider": provider, "response_id": response.id, "records": records, "judgments": judgments}
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Company CSV with the answer key.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="One folder of saved cells per provider.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--only", help="comma-separated providers")
    parser.add_argument("--max-workers", type=int, default=11)
    args = parser.parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")
    cases = list(csv.DictReader(args.input.open(newline="", encoding="utf-8")))
    providers = sorted(path.name for path in args.raw_dir.iterdir() if path.is_dir() and not path.name.endswith("-batches"))
    if args.only:
        providers = [provider for provider in providers if provider in {value.strip() for value in args.only.split(",")}]
    tasks = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for provider in providers:
        rows = []
        for case in cases:
            path = args.raw_dir / provider / f"{case['company_domain']}.json"
            if not path.exists():
                raise RuntimeError(f"{provider}: no saved cell for {case['company_domain']}")
            rows.append(record(case, json.loads(path.read_text())))
        for index, group in enumerate(chunks(sorted(rows, key=lambda row: row["record_id"]), BATCH_SIZE), start=1):
            tasks.append((provider, group, args.output_dir / f"{provider}-{index}.json"))
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(judge, *task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            print(json.dumps({"provider": result["provider"], "response_id": result["response_id"], "records": len(result["records"])}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
