#!/usr/bin/env python3
"""Rate-limited Crustdata funding enrichment for the benchmark cohort."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "sample.csv"
RAW = ROOT / "runs" / "raw" / "crustdata"
BATCH_RAW = ROOT / "runs" / "raw" / "crustdata-batches"
URL = "https://api.crustdata.com/company/enrich"
CHUNK_SIZE = 25  # API maximum.
REQUEST_INTERVAL_SECONDS = 4.1  # 14.6 requests/minute; API limit is 15.


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(body, indent=2) + "\n")
    temporary.replace(path)


def is_final(path: Path) -> bool:
    if not path.exists():
        return False
    return json.loads(path.read_text()).get("status") in {"ok", "not_found"}


def choose(matches: list[dict], domain: str) -> dict | None:
    if not matches:
        return None
    # Highest confidence wins; exact primary-domain match resolves score ties.
    return max(matches, key=lambda match: (
        match.get("confidence_score") or 0,
        (((match.get("company_data") or {}).get("basic_info") or {}).get("primary_domain") or "").lower() == domain.lower(),
    ))


def request(domains: list[str]) -> list[dict]:
    headers = {
        "authorization": f"Bearer {os.environ['CRUSTDATA_API_KEY']}",
        "content-type": "application/json",
        "x-api-version": "2025-11-01",
    }
    payload = json.dumps({"domains": domains, "exact_match": True, "fields": ["funding"]}).encode()
    with urlopen(Request(URL, data=payload, headers=headers, method="POST"), timeout=120) as response:
        return json.loads(response.read())


def main() -> int:
    # Cohort size and location are arguments now: freshness snapshots are their
    # own cohorts, separate from the frozen enrichment input.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--batch-dir", type=Path, default=BATCH_RAW)
    args = parser.parse_args()
    raw, batch_raw = args.raw_dir, args.batch_dir
    if not os.environ.get("CRUSTDATA_API_KEY"):
        raise RuntimeError("CRUSTDATA_API_KEY is required")
    cases = list(csv.DictReader(args.input.open(newline="", encoding="utf-8")))
    if not cases:
        raise RuntimeError(f"{args.input} has no rows")
    pending = [case for case in cases if not is_final(raw / f"{case['company_domain']}.json")]
    print(json.dumps({"total": len(cases), "saved": len(cases) - len(pending), "pending": len(pending), "chunk_size": CHUNK_SIZE, "request_interval_seconds": REQUEST_INTERVAL_SECONDS}), flush=True)
    for index in range(0, len(pending), CHUNK_SIZE):
        group = pending[index:index + CHUNK_SIZE]
        started = time.perf_counter()
        try:
            response = request([case["company_domain"] for case in group])
            # Save the complete paid response before parsing any individual row.
            # This makes a parser failure recoverable without another API call.
            write(batch_raw / f"{index // CHUNK_SIZE + 1:02d}-{now().replace(':', '-')}.json", {
                "requested_domains": [case["company_domain"] for case in group],
                "completed_at": now(), "response": response,
            })
            by_input = {item.get("matched_on", "").lower(): item for item in response}
            for case in group:
                domain = case["company_domain"]
                envelope = by_input.get(domain.lower(), {})
                selected = choose(envelope.get("matches") or [], domain)
                company_data = (selected or {}).get("company_data") or {}
                normalized = company_data.get("funding") or {}
                row = {
                    "provider": "crustdata", "case_slug": case["candidate_id"],
                    "input": {"company_name": case["company_name"], "domain": domain},
                    "source": "live_api", "completed_at": now(),
                    "status": "ok" if company_data else "not_found",
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "normalized": {
                        "latest_stage": normalized.get("last_round_type"),
                        "latest_announced_on": normalized.get("last_fundraise_date"),
                        "latest_amount": normalized.get("last_round_amount_usd"),
                        "currency": "USD" if normalized.get("last_round_amount_usd") is not None else None,
                        "total_raised": normalized.get("total_investment_usd"),
                    },
                    "raw": {"envelope": envelope, "selected_match": selected},
                }
                write(raw / f"{domain}.json", row)
        except Exception as error:
            for case in group:
                write(raw / f"{case['company_domain']}.json", {
                    "provider": "crustdata", "case_slug": case["candidate_id"],
                    "input": {"company_name": case["company_name"], "domain": case["company_domain"]},
                    "source": "live_api", "completed_at": now(), "status": "error",
                    "failure_reason": f"{type(error).__name__}: {error}",
                    "latency_ms": round((time.perf_counter() - started) * 1000), "normalized": {},
                })
        print(json.dumps({"batch": index // CHUNK_SIZE + 1, "of": (len(pending) + CHUNK_SIZE - 1) // CHUNK_SIZE, "saved": min(index + CHUNK_SIZE, len(pending))}), flush=True)
        if index + CHUNK_SIZE < len(pending):
            time.sleep(REQUEST_INTERVAL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
