"""Normalized search result metadata."""
from typing import TypedDict


class SearchResult(TypedDict, total=False):
    title: str
    url: str
    source_domain: str
    snippet: str
    retrieved_at: str
    published_at: str | None
    source_type: str
    confidence: str
    relevance: str
