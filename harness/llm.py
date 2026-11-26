"""The OpenAI client for the extraction step of the search providers and for the judge.

The model is served by Azure OpenAI when `AZURE_OPENAI_BASE_URL` (the deployment's OpenAI v1 URL, ending in
`/openai/v1`) and `AZURE_OPENAI_API_KEY` are set, and by OpenAI with `OPENAI_API_KEY` otherwise. On Azure, the model
names in this repo are deployment names.
"""
from __future__ import annotations

import os
from typing import Any


def provider() -> str | None:
    """"azure" or "openai", by the credentials set; None when neither is."""
    if os.getenv("AZURE_OPENAI_BASE_URL") and os.getenv("AZURE_OPENAI_API_KEY"):
        return "azure"
    return "openai" if os.getenv("OPENAI_API_KEY") else None


def missing() -> list[str]:
    """The credential names to report when no model provider is configured."""
    return [] if provider() else ["AZURE_OPENAI_BASE_URL and AZURE_OPENAI_API_KEY, or OPENAI_API_KEY"]


def client(**options: Any) -> Any:
    from openai import OpenAI

    if provider() == "azure":
        return OpenAI(base_url=os.environ["AZURE_OPENAI_BASE_URL"].rstrip("/"), api_key=os.environ["AZURE_OPENAI_API_KEY"], **options)
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"], **options)
