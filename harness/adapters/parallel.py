"""Parallel: a Task API run at a processor (parallel), or one Responses request at a reasoning effort."""
from __future__ import annotations

import json
import time
from typing import Any

from ..models import Answer, Company
from ..question import OUTPUT_SCHEMA, funding_fields, instruction, responses_output
from ._research import ResearchAdapter

TASK_POLLS = 36
TASK_POLL_SECONDS = 5


class Parallel(ResearchAdapter):
    def lookup(self, company: Company) -> Answer:
        return self._responses(company) if "reasoning_effort" in self.settings else self._task(company)

    def _task(self, company: Company) -> Answer:
        headers = {"x-api-key": self.key("PARALLEL_API_KEY"), "Content-Type": "application/json"}
        payload = {
            "input": {"company_name": company.name or company.domain, "company_website": company.domain,
                      "instruction": instruction(company)},
            "processor": self.settings["processor"],
            "task_spec": {
                "input_schema": {"type": "json", "json_schema": {"type": "object", "properties": {
                    "company_name": {"type": "string"}, "company_website": {"type": "string"}, "instruction": {"type": "string"}},
                    "required": ["company_name", "company_website", "instruction"]}},
                "output_schema": {"type": "json", "json_schema": OUTPUT_SCHEMA},
            },
        }
        started = time.perf_counter()
        created = self.call("POST", "https://api.parallel.ai/v1/tasks/runs", headers, payload).body or {}
        run_id = created["run_id"]
        for _ in range(TASK_POLLS):
            # 202 and 404 mean the run is not ready yet.
            response = self.call("GET", f"https://api.parallel.ai/v1/tasks/runs/{run_id}/result", headers,
                                 ok_statuses=frozenset({202, 404}))
            result = response.body if response.ok and isinstance(response.body, dict) else None
            if result and (result.get("status") in {"completed", "succeeded"} or result.get("output")):
                return self.answer(company, "ok", funding_fields(result["output"]["content"]),
                                   latency_ms=round((time.perf_counter() - started) * 1000),
                                   cost_units=1, cost_unit="task run", raw={"created": created, "result": result})
            time.sleep(TASK_POLL_SECONDS)
        raise TimeoutError(f"Parallel Task {run_id} did not complete within three minutes")

    def _responses(self, company: Company) -> Answer:
        headers = {"Authorization": f"Bearer {self.key('PARALLEL_API_KEY')}", "Content-Type": "application/json"}
        payload = {"model": self.settings["model"], "input": instruction(company),
                   "reasoning": {"effort": self.settings["reasoning_effort"]},
                   "text": {"format": {"type": "json_schema", "name": "funding_event", "schema": OUTPUT_SCHEMA}}}
        response = self.call("POST", "https://api.parallel.ai/v1/responses", headers, payload)
        body = response.body if isinstance(response.body, dict) else {}
        text, citations = responses_output(body)
        if text is None:
            raise ValueError("Parallel Responses returned no output text")
        try:
            normalized = json.loads(text)
        except json.JSONDecodeError:
            normalized = {"unparsed_text": text}  # Prose instead of the schema is the result; it scores nothing.
        return self.answer(company, "ok", funding_fields(normalized), latency_ms=response.latency_ms,
                           cost_units=1, cost_unit="request", raw={"response": body, "sources": citations})


def build(setup: str, spec: dict[str, Any], env: list[str]) -> Parallel:
    return Parallel(setup, spec, env)
