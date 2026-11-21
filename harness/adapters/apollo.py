"""Apollo organization enrichment by domain."""
from __future__ import annotations

from typing import Any

from ..http_client import Response
from ..models import Company
from ._common import DataApiAdapter, latest_round


class Apollo(DataApiAdapter):
    def call(self, company: Company) -> Response:
        return self.get("https://api.apollo.io/api/v1/organizations/enrich",
                        headers={"x-api-key": self.key("APOLLO_API_KEY"), "Accept": "application/json"},
                        params={"domain": company.domain})

    def not_found(self, body: dict[str, Any]) -> str | None:
        return None if body.get("organization") else "no organization"

    def parse(self, body: dict[str, Any]) -> dict[str, Any]:
        item = body.get("organization") or {}
        result = latest_round(item.get("funding_events") or [], date_key="date", stage_key="type", amount_key="amount")
        result["latest_stage"] = item.get("latest_funding_stage") or result["latest_stage"]
        result["latest_date"] = item.get("latest_funding_round_date") or result["latest_date"]
        result["total_raised"] = item.get("total_funding")
        return result


def build(setup: str, spec: dict[str, Any], env: list[str]) -> Apollo:
    return Apollo(setup, spec, env)
