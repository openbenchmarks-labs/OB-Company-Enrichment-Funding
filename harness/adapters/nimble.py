"""Nimble: Search plus extraction (nimble-lite, nimble-standard), or one isolated Agents run per company."""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from .. import http_client
from ..models import Answer, Company
from ..question import OUTPUT_SCHEMA, funding_fields, instruction, validate_output
from ._extraction import extract
from ._research import HttpError, ResearchAdapter

SEARCH_URL = "https://sdk.nimbleway.com/v2/search"
RUNS_URL = "https://sdk.nimbleway.com/v2/agents/runs"
RUN_TIMEOUT_SECONDS = 1800
POLL_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 60
CREATE_ATTEMPTS = 4  # A new run is retried only after HTTP 429, so a run is never started twice.
TERMINAL = {"completed", "failed", "cancelled"}


class Nimble(ResearchAdapter):
    def lookup(self, company: Company) -> Answer:
        return self._agent(company) if "use_case" in self.settings else self._search(company)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key('NIMBLE_API_KEY')}", "Content-Type": "application/json"}

    def _search(self, company: Company) -> Answer:
        s = self.settings
        payload = {"query": instruction(company), "search_depth": s["search_depth"], "full_content": s["full_content"],
                   "focus": s["focus"], "max_results": s["max_results"]}
        response = self.call("POST", SEARCH_URL, self._headers(), payload, timeout=60, attempts=1)
        body = response.body if isinstance(response.body, dict) else {}
        if not isinstance(body.get("results"), list):
            raise ValueError("Nimble returned no results array")
        hits = search_hits(body, s["max_results"])
        raw: dict[str, Any] = {"response": body, "search_evidence": hits}
        if body["results"] and not hits:
            raise ValueError("Nimble returned results without usable URLs")
        if not hits:
            return self.answer(company, "not_found", funding_fields({}), latency_ms=response.latency_ms,
                               cost_units=1, cost_unit="search", raw=raw)
        value, audit = extract(company, hits, s["extractor"])
        raw["extraction"] = audit
        status = "ok" if any(v is not None for v in value.values()) else "not_found"
        return self.answer(company, status, funding_fields(value), latency_ms=response.latency_ms + audit["latency_ms"],
                           cost_units=1, cost_unit="search", raw=raw)

    def _agent(self, company: Company) -> Answer:
        started = time.monotonic()

        def remaining() -> float:
            left = RUN_TIMEOUT_SECONDS - (time.monotonic() - started)
            if left <= 0:
                raise TimeoutError("Nimble agent timed out; the remote run may still be active")
            return left

        headers = self._headers()
        body = {"use_case": self.settings["use_case"], "effort": self.settings["effort"], "input": instruction(company),
                "input_data": {"primary_domain": company.domain}, "output_schema": OUTPUT_SCHEMA}
        for attempt in range(1, CREATE_ATTEMPTS + 1):
            created = http_client.request("POST", RUNS_URL, headers=headers, json=body,
                                          timeout=min(REQUEST_TIMEOUT_SECONDS, remaining()), attempts=1)
            if created.status != 429 or attempt == CREATE_ATTEMPTS:
                break
            time.sleep(min(60, 2 ** attempt))
        if not created.ok:
            raise HttpError(created)
        state = created.body if isinstance(created.body, dict) else {}
        raw: dict[str, Any] = {"create_response": state, "polls": []}
        agent_id, run_id = state.get("web_search_agent_id"), state.get("id")
        if not all(isinstance(v, str) and v.strip() for v in (agent_id, run_id)):
            raise ValueError("Nimble Agents returned no agent or run ID")
        url = f"https://sdk.nimbleway.com/v2/agents/{quote(agent_id, safe='')}/runs/{quote(run_id, safe='')}"
        while _status(state) not in TERMINAL:
            time.sleep(min(POLL_SECONDS, remaining()))
            state = self.call("GET", url, headers, timeout=min(REQUEST_TIMEOUT_SECONDS, remaining())).body or {}
            raw["polls"].append(state)
        if state["status"] != "completed":
            raise ValueError(f"Nimble agent run {state['status']}: {state.get('error') or state.get('error_message') or ''}")
        result = self.call("GET", url + "/result", headers, timeout=min(REQUEST_TIMEOUT_SECONDS, remaining())).body or {}
        raw["response"] = result
        output = result.get("output") if isinstance(result, dict) else None
        if not isinstance(output, dict) or output.get("type") != "json":
            raise ValueError("Nimble Agents returned no JSON output")
        content = output.get("content")
        value = validate_output(dict(content) if isinstance(content, dict) else content)
        status = "ok" if any(v is not None for v in value.values()) else "not_found"
        return self.answer(company, status, funding_fields(value), latency_ms=round((time.monotonic() - started) * 1000),
                           cost_units=1, cost_unit="agent run", raw=raw)


def _status(state: Any) -> str:
    value = state.get("status") if isinstance(state, dict) else None
    if value not in TERMINAL | {"queued", "running"}:
        raise ValueError(f"Nimble Agents returned an invalid run status: {value!r}")
    return value


def search_hits(payload: dict[str, Any], max_results: int) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in payload.get("results") or []:
        if not isinstance(row, dict) or not isinstance(row.get("url"), str):
            continue
        url = row["url"].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        hits.append({"url": url, "title": str(row.get("title") or ""), "snippet": str(row.get("description") or "")})
        if len(hits) >= max_results:
            break
    return hits


def build(setup: str, spec: dict[str, Any], env: list[str]) -> Nimble:
    return Nimble(setup, spec, env)
