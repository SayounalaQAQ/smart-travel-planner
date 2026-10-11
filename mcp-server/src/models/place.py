"""Normalized mapped place and place-detail records; absent facts are nullable."""
from typing import TypedDict


class PlaceRecord(TypedDict, total=False):
    name: str
    category: str | None
    lat: float | None
    lon: float | None
    address: str | None
    official_url: str | None
    source: str
    source_confidence: str


class PlaceDetails(TypedDict, total=False):
    name: str
    address: str | None
    coordinates: dict | None
    official_url: str | None
    opening_hours: str | None
    ticket: str | None
    reservation: str | None
    recommended_duration: str | None
    nearest_station: str | None
    category: str | None
    sources: list
    retrieved_at: str
    confidence: str
