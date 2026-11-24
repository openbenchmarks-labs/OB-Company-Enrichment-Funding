"""Shared Nimble request shapes and source-only response parsing."""

from __future__ import annotations

from typing import Any

SEARCH_URL = "https://sdk.nimbleway.com/v2/search"
SEARCH_PRICES = {"lite": 0.0011, "standard": 0.005}


def search_body(query: str, depth: str, max_results: int) -> dict[str, Any]:
    if depth not in SEARCH_PRICES:
        raise ValueError(f"Unsupported Nimble search depth: {depth}")
    return {"query": query, "search_depth": depth, "full_content": False,
            "focus": "general", "max_results": max_results}


def search_hits(payload: Any, max_results: int) -> list[dict[str, str]]:
    rows = payload.get("results") if isinstance(payload, dict) else None
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("url"), str):
            continue
        url = row["url"].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        hits.append({"url": url, "title": str(row.get("title") or ""),
                     "snippet": str(row.get("description") or "")})
        if len(hits) >= max_results:
            break
    return hits
