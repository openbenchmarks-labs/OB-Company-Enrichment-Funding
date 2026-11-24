"""Nimble Agents funding enrichment, with one isolated remote run per company."""

from __future__ import annotations

import json
import math
import os
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse

from harness.nimble_search import contract_hash, validate_output


VENDOR_SLUG = "nimble-agents"
VENDOR_NAME = "Nimble Agents"
REQUIRED_ENV = ("NIMBLE_API_KEY",)
RUNS_URL = "https://sdk.nimbleway.com/v2/agents/runs"
USE_CASE = "enrichment"
EFFORT = "high"
RUN_TIMEOUT_S = 1800
POLL_INTERVAL_S = 10
REQUEST_TIMEOUT_S = 60
DEFAULT_CONCURRENCY = 5
MAX_RETRIES_PER_INPUT = 3
HTTP_MAX_ATTEMPTS = MAX_RETRIES_PER_INPUT + 1
RETRY_BASE_DELAY_S = 2
RETRY_MAX_DELAY_S = 60
GET_RETRY_STATUSES = {429, 500, 502, 503, 504}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class FundingAgentError(RuntimeError):
    """Keep remote identifiers and paid responses when a run fails locally."""

    def __init__(self, error: Exception, audit: dict[str, Any]):
        super().__init__(f"{type(error).__name__}: {error}")
        self.audit = audit


def contract(case: dict[str, str], query: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "funding-nimble-agents-v2",
        "request": {
            "method": "POST", "url": RUNS_URL,
            "body": {
                "use_case": USE_CASE, "effort": EFFORT, "input": query,
                # Identity only; labels and prior agent memory are never supplied.
                "input_data": {"primary_domain": case["company_domain"]},
                "output_schema": schema,
            },
        },
        "run_timeout_seconds": RUN_TIMEOUT_S,
        "poll_interval_seconds": POLL_INTERVAL_S,
        "request_timeout_seconds": REQUEST_TIMEOUT_S,
        "http_max_attempts": HTTP_MAX_ATTEMPTS,
        "retry_policy": {
            "max_retries_per_input": MAX_RETRIES_PER_INPUT,
            "create_http_statuses": [429], "get_http_statuses": sorted(GET_RETRY_STATUSES),
            "get_transport_errors": True, "create_transport_errors": False,
            "base_delay_seconds": RETRY_BASE_DELAY_S, "max_exponential_delay_seconds": RETRY_MAX_DELAY_S,
            "jitter_seconds": 1, "honor_retry_after": True,
            "bounded_by_run_deadline": True,
        },
    }


def retry_delay(attempt: int, error: HTTPError | None = None) -> float:
    """Respect server delays (seconds, HTTP dates, or JSON), with jitter."""
    hints: list[Any] = []
    if error is not None:
        header = error.headers.get("Retry-After") if error.headers else None
        if header:
            try:
                hints.append(float(header))
            except ValueError:
                try:
                    hints.append(parsedate_to_datetime(header).timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
        try:
            body = json.loads(error.read(65536))
            if isinstance(body, dict):
                hints.append(body.get("retry_after"))
                if isinstance(body.get("error"), dict):
                    hints.append(body["error"].get("retry_after"))
        except (ValueError, TypeError, OSError):
            pass
        finally:
            error.close()
    delay = min(RETRY_MAX_DELAY_S, RETRY_BASE_DELAY_S * 2 ** (attempt - 1))
    for hint in hints:
        try:
            seconds = float(hint)
            if math.isfinite(seconds):
                delay = max(delay, seconds)
        except (ValueError, TypeError):
            pass
    return delay + random.uniform(0, 1)


def parse_result(payload: Any, schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    output = payload.get("output") if isinstance(payload, dict) else None
    if not isinstance(output, dict) or output.get("type") != "json":
        raise ValueError("Nimble Agents returned no JSON output")
    content = output.get("content")
    # Validate a copy so normalization cannot alter the retained raw response.
    value = validate_output(dict(content) if isinstance(content, dict) else content, schema)
    sources = []
    trust = output.get("trust")
    claims = trust.get("claims") if isinstance(trust, dict) else None
    for claim in claims if isinstance(claims, list) else []:
        citations = claim.get("citations") if isinstance(claim, dict) else None
        for citation in citations if isinstance(citations, list) else []:
            url = citation.get("url") if isinstance(citation, dict) else None
            if isinstance(url, str):
                try:
                    parsed = urlparse(url)
                except ValueError:
                    continue
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    sources.append(url)
    return value, list(dict.fromkeys(sources))


def run(
    case: dict[str, str], *, query: str, schema: dict[str, Any],
    request: Callable[..., dict[str, Any]],
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    request_contract = contract(case, query, schema)
    audit: dict[str, Any] = {
        "contract": request_contract, "contract_sha256": contract_hash(request_contract),
        "request": request_contract["request"], "use_case": USE_CASE, "effort": EFFORT,
        "status": "in_progress", "run_accepted": False, "polls": [], "sources": [],
        "http_retries": [],
        "cost_units": None, "cost_unit": "nimble_agent_run",
        "cost_scope": "Accepted agent runs counted; USD pricing not configured. Not an invoice.",
    }

    def save() -> None:
        if checkpoint:
            checkpoint(audit)

    def remaining() -> float:
        seconds = RUN_TIMEOUT_S - (time.monotonic() - started)
        if seconds <= 0:
            raise TimeoutError("Nimble agent timed out; remote run may still be active; inspect audit run_id before retrying")
        return seconds

    def status(state: Any) -> str:
        value = state.get("status") if isinstance(state, dict) else None
        if value not in TERMINAL_STATUSES | {"queued", "running"}:
            raise ValueError(f"Nimble Agents returned an invalid run status: {value!r}")
        return value

    def call(url: str, headers: dict[str, str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        creating = payload is not None
        for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
            http_error = None
            # Deadline expiry is not a transport failure and must not be retried.
            timeout = min(REQUEST_TIMEOUT_S, remaining())
            try:
                args = (url, headers, payload) if creating else (url, headers)
                return request(*args, timeout=timeout)
            except HTTPError as error:
                # Only a definite rate-limit refusal is safe to repeat on POST.
                # GET retries always refer to the same accepted remote run.
                if error.code not in ({429} if creating else GET_RETRY_STATUSES) or len(audit["http_retries"]) >= MAX_RETRIES_PER_INPUT:
                    raise
                http_error = error
                reason = f"HTTP {error.code}"
                delay = retry_delay(len(audit["http_retries"]) + 1, error)
            except (URLError, TimeoutError, ConnectionError) as error:
                if creating or len(audit["http_retries"]) >= MAX_RETRIES_PER_INPUT:
                    raise
                reason = type(error).__name__
                delay = retry_delay(len(audit["http_retries"]) + 1)
            audit["http_retries"].append({
                "method": "POST" if creating else "GET", "url": url, "attempt": attempt,
                "retry_number": len(audit["http_retries"]) + 1,
                "reason": reason, "http_status": http_error.code if http_error else None,
                "backoff_seconds": delay,
            })
            save()
            if delay >= remaining():
                raise TimeoutError("Nimble retry delay exceeds the remaining run deadline; inspect saved remote IDs")
            time.sleep(delay)
        raise RuntimeError("unreachable")

    try:
        if not os.environ.get("NIMBLE_API_KEY"):
            raise RuntimeError("NIMBLE_API_KEY is required")
        headers = {"Authorization": f"Bearer {os.environ['NIMBLE_API_KEY']}",
                   "Content-Type": "application/json"}
        save()
        state = call(RUNS_URL, headers, request_contract["request"]["body"])
        audit.update(create_response=state, run_accepted=True, cost_units=1)
        agent_id = state.get("web_search_agent_id") if isinstance(state, dict) else None
        run_id = state.get("id") if isinstance(state, dict) else None
        audit.update(agent_id=agent_id, run_id=run_id)
        save()
        if not all(isinstance(value, str) and value.strip() for value in (agent_id, run_id)):
            raise ValueError("Nimble Agents returned no agent or run ID")
        url = ("https://sdk.nimbleway.com/v2/agents/" + quote(agent_id, safe="")
               + "/runs/" + quote(run_id, safe=""))
        while status(state) not in TERMINAL_STATUSES:
            time.sleep(min(POLL_INTERVAL_S, remaining()))
            state = call(url, headers)
            audit["polls"].append(state)
            save()
        if state["status"] != "completed":
            raise RuntimeError(f"Nimble agent run {state['status']}: {state.get('error') or state.get('error_message') or ''}")
        result = call(url + "/result", headers)
        audit["raw_response"] = result
        save()
        value, sources = parse_result(result, schema)
        audit.update(sources=sources, status="ok" if any(v is not None for v in value.values()) else "not_found")
        return value, audit
    except Exception as error:
        audit["status"] = "error"
        raise FundingAgentError(error, audit) from error
    finally:
        audit["agent_latency_ms"] = round((time.monotonic() - started) * 1000)
