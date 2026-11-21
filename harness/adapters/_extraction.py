"""Search-then-extract: an OpenAI model reads a tool's search results and fills the funding schema from them only."""
from __future__ import annotations

import json
from typing import Any

from .. import llm
from ..models import Company
from ..question import OUTPUT_SCHEMA, SEARCH_EXTRACTION_PROMPT, instruction, validate_output


def user_content(company: Company, hits: list[dict[str, Any]]) -> str:
    """The user message the extraction model reads: the company, the question and the search results."""
    return json.dumps({"company_name": company.name or company.domain, "company_domain": company.domain,
                       "instruction": instruction(company), "results": hits})


def extract(company: Company, hits: list[dict[str, Any]], extractor: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the validated answer and the extraction audit. `extractor` is the setup's `extractor` settings."""
    value, audit = llm.extract(
        system_prompt=SEARCH_EXTRACTION_PROMPT,
        user_content=user_content(company, hits),
        schema=OUTPUT_SCHEMA, schema_name="funding_event", model=extractor["model"],
        reasoning_effort=extractor["reasoning_effort"], max_output_tokens=int(extractor.get("max_output_tokens", 4000)),
        timeout=float(extractor.get("timeout_seconds", 180)),
    )
    return validate_output(value), audit
