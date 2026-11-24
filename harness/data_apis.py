"""Requests to the funding data APIs. Each takes a company domain and returns the raw response."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 45


def load_environment() -> None:
    load_dotenv(ROOT / ".env", override=False)


def response_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"non_json_body": response.text[:2000]}


def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    body = response_body(response)
    return {
        "http_status": response.status_code,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "response": body,
        "rate_limit": {
            key.lower(): value
            for key, value in response.headers.items()
            if key.lower() in {"retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "ratelimit-limit", "ratelimit-remaining", "x-call-credits-spent"}
        },
    }


def fiber(domain: str) -> dict[str, Any]:
    return request(
        "POST", "https://api.fiber.ai/v1/company-search",
        json={
            "apiKey": os.environ["FIBER_API_KEY"],
            "searchParams": {
                "exactCompanyV2": {"anyOf": [{"identifier": "domain", "domain": domain}]}
            },
        },
    )


def predictleads(domain: str) -> dict[str, Any]:
    return request(
        "GET", f"https://predictleads.com/api/v3/companies/{domain}/financing_events",
        headers={"X-Api-Key": os.environ["PREDICT_LEADS_API_KEY"], "X-Api-Token": os.environ["PREDICT_LEADS_API_TOKEN"], "Accept": "application/json"},
    )


def apollo(domain: str) -> dict[str, Any]:
    return request(
        "GET", "https://api.apollo.io/api/v1/organizations/enrich",
        headers={"x-api-key": os.environ["APOLLO_API_KEY"], "Accept": "application/json"},
        params={"domain": domain},
    )


def people_data_labs(domain: str) -> dict[str, Any]:
    return request(
        "GET", "https://api.peopledatalabs.com/v5/company/enrich",
        headers={"X-Api-Key": os.environ["PEOPLE_DATA_LABS_API_KEY"], "Accept": "application/json"},
        params={"website": domain},
    )


def ocean(domain: str) -> dict[str, Any]:
    fields = ["domain", "name", "fundingRound", "fundingRound.date", "fundingRound.type", "fundingRound.moneyRaisedInUsd", "rootUrl"]
    return request(
        "POST", "https://api.ocean.io/v2/enrich/company",
        headers={"X-Api-Token": os.environ["OCEAN_API_KEY"], "Accept": "application/json", "Content-Type": "application/json"},
        json={"company": {"domain": domain}, "fields": fields},
    )


def explorium(domain: str) -> dict[str, Any]:
    headers = {"api_key": os.environ["EXPLORIUM_API_KEY"], "Content-Type": "application/json"}
    matched = request(
        "POST", "https://api.explorium.ai/v1/businesses/match", headers=headers,
        json={"businesses_to_match": [{"domain": domain}]},
    )
    if not 200 <= matched["http_status"] < 300:
        return {"match": matched}
    body = matched["response"]
    candidates = body.get("matched_businesses", []) if isinstance(body, dict) else []
    business_id = next((item.get("business_id") or item.get("businessId") for item in candidates if isinstance(item, dict)), None)
    if not business_id:
        return {"match": matched, "error": "match returned no business_id"}
    enriched = request(
        "POST", "https://api.explorium.ai/v1/businesses/funding_and_acquisition/bulk_enrich",
        headers=headers, json={"business_ids": [business_id]},
    )
    return {"match": matched, "funding_enrichment": enriched}


def company_enrich(domain: str) -> dict[str, Any]:
    return request(
        "GET", "https://api.companyenrich.com/companies/enrich",
        headers={"Authorization": f"Bearer {os.environ['COMPANY_ENRICH_API_KEY']}", "Accept": "application/json"},
        params={"domain": domain},
    )


def fundable(domain: str) -> dict[str, Any]:
    return request(
        "GET", "https://www.tryfundable.ai/api/v1/company",
        headers={"Authorization": f"Bearer {os.environ['FUNDABLE_API_KEY']}", "Accept": "application/json"},
        params={"domain": domain},
    )


PROVIDERS: dict[str, tuple[tuple[str, ...], Callable[[str], dict[str, Any]]]] = {
    "fiber": (("FIBER_API_KEY",), fiber),
    "predictleads": (("PREDICT_LEADS_API_KEY", "PREDICT_LEADS_API_TOKEN"), predictleads),
    "apollo": (("APOLLO_API_KEY",), apollo),
    "people-data-labs": (("PEOPLE_DATA_LABS_API_KEY",), people_data_labs),
    "ocean": (("OCEAN_API_KEY",), ocean),
    "explorium": (("EXPLORIUM_API_KEY",), explorium),
    "company-enrich": (("COMPANY_ENRICH_API_KEY",), company_enrich),
    "fundable": (("FUNDABLE_API_KEY",), fundable),
}


def funding_paths(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if any(term in key.lower() for term in ("fund", "round", "investment", "amount", "raised", "valuation")):
                hits.append(child_path)
            hits.extend(funding_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value[:5]):
            hits.extend(funding_paths(child, f"{path}[{index}]"))
    return hits
