"""obkit hooks: one setup's answer per company, what the setups see first, and the request each setup sends."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any
from unittest import mock

from . import http_client, registry
from .adapters._extraction import user_content
from .adapters._research import HttpError
from .models import FIELDS, Company
from .question import SEARCH_EXTRACTION_PROMPT, OUTPUT_SCHEMA, instruction

PROBE_COMPANY = Company("example.com", "Example Company")


def answer(question: dict[str, Any], setup: str, *, dry: bool, tracer: Any = None) -> dict[str, Any]:
    """One setup's answer for one question row. `dry` returns a canned reply and sends nothing.

    The `answer` string is always the three graded fields as JSON, null where the setup gave no value.
    A vendor's 429 or 5xx, and a failure of ours, raise so obkit records an infra_error with the full hold.
    `tracer` is accepted for obkit's signature and not used.
    """
    company = Company(question["domain"], question.get("company") or None)
    if dry:
        return _canned(question, setup)
    try:
        found = registry.build(setup).lookup(company)
    except HttpError as exc:
        return _failed(exc.response.status, str(exc))
    except http_client.HTTPError as exc:
        return _failed(exc.status, str(exc))
    except ValueError as exc:  # the vendor's answer did not parse
        return _row("vendor_error", error=f"{type(exc).__name__}: {exc}")
    if found.status == "not_found":
        return _row("vendor_empty", error=found.error)
    if found.status == "error":
        return _failed(_status_code(found.error), found.error or "")
    status = "ok" if any(found.fields.get(f) is not None for f in FIELDS) else "vendor_empty"
    return _row(status, found.fields, cost_usd=float(found.cost_units or 0) if found.cost_unit == "usd" else 0.0)


def contract(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """What a setup sees first, per question. No network. The search-then-extract user message is shown with no results."""
    companies = [Company(q["domain"], q.get("company") or None) for q in questions]
    return {
        "output_schema": OUTPUT_SCHEMA,
        "extraction_system_prompt": SEARCH_EXTRACTION_PROMPT,
        "per_question": {c.domain: {"instruction": instruction(c), "extraction_user_content": user_content(c, [])}
                         for c in companies},
    }


def probe(setup: str) -> dict[str, Any]:
    """The first request `setup` sends for PROBE_COMPANY, recorded offline. Keys are replaced with placeholders."""
    adapter = registry.build(setup)
    sent: dict[str, Any] = {}

    class _Captured(Exception):
        pass

    def fake_request(method: str, url: str, **kwargs: Any) -> None:
        sent.update(method=method, url=url, **kwargs)
        raise _Captured

    def fake_run(args: Any, **_: Any) -> None:
        argv = list(args)
        if "--file" in argv:  # the CLI reads its payload from a temp file whose name is random
            with open(argv[argv.index("--file") + 1]) as handle:
                argv[argv.index("--file") + 1] = json.load(handle)
        sent.update(argv=argv)
        raise _Captured

    placeholders = {name: "probe-placeholder" for name in adapter.env}
    with mock.patch.dict(os.environ, placeholders), \
            mock.patch.object(http_client, "request", fake_request), \
            mock.patch.object(subprocess, "run", fake_run):
        try:
            adapter.lookup(PROBE_COMPANY)
        except Exception:
            if not sent:
                raise
    if not sent:
        raise RuntimeError(f"{setup} sent no request for the probe company")
    return sent


def _row(status: str, fields: dict[str, Any] | None = None, *, error: str | None = None, cost_usd: float = 0.0) -> dict[str, Any]:
    values = {f: (fields or {}).get(f) for f in FIELDS}
    return {"status": status, "answer": json.dumps(values), "error": error, "cost_usd": cost_usd}


def _failed(code: int | None, message: str) -> dict[str, Any]:
    """429 and 5xx are our rate limits or the vendor's outage: raise, so the row is infra_error. Other errors are the vendor's."""
    if code == 429 or (code is not None and code >= 500):
        raise RuntimeError(message)
    return _row("vendor_error", error=message[:300])


def _status_code(error: str | None) -> int | None:
    """The status in a "HTTP 429: ..." error, as http_failure writes it."""
    if not error or not error.startswith("HTTP "):
        return None
    digits = error[5:8]
    return int(digits) if digits.isdigit() else None


def _canned(question: dict[str, Any], setup: str) -> dict[str, Any]:
    """A reply with no network: the question's truth, or the amount doubled, chosen by a hash of setup and domain."""
    truth = {f: question[f] for f in FIELDS}
    odd = hashlib.sha256(f"{setup}|{question['domain']}".encode()).digest()[0] % 2
    fields = dict(truth, amount=truth["amount"] * 2) if odd else truth
    return _row("ok", fields)
