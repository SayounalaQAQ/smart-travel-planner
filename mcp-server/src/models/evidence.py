"""Normalized, provenance-preserving evidence records (legacy keys retained)."""
from typing import TypedDict


class EvidenceRecord(TypedDict, total=False):
    id: str
    claim: str
    source_title: str
    source_url: str
    source_type: str
    source_domain: str
    retrieved_at: str
    published_at: str | None
    evidence: str
    confidence: str
    # V0.4 compatibility fields consumed by existing MCP envelopes/scripts.
    value: str
    checked_at: str
    applicable_date: str | None


def record(claim, value, title, url, source_type, checked_at, applicable_date=None,
           confidence='medium', *, published_at=None, evidence=None, record_id=None):
    import hashlib
    from urllib.parse import urlsplit
    record_id = record_id or hashlib.sha256(f"{claim}|{url}|{checked_at}".encode("utf-8")).hexdigest()[:16]
    return EvidenceRecord(
        id=record_id, claim=claim, value=str(value), evidence=str(evidence if evidence is not None else value),
        source_title=title, source_url=url, source_domain=urlsplit(url).hostname or '',
        source_type=source_type, checked_at=checked_at, retrieved_at=checked_at,
        applicable_date=applicable_date, published_at=published_at, confidence=confidence)
