"""Replaceable POI provider boundary and normalized place records."""
from abc import ABC, abstractmethod


class PlacesProvider(ABC):
    name = "places-provider"

    @abstractmethod
    def search(self, query, location, category=None, radius=3000):
        raise NotImplementedError


class PlaceDetailsProvider(ABC):
    name = "place-details-provider"

    @abstractmethod
    def details(self, place_name, location):
        raise NotImplementedError


class CallbackPlacesProvider(PlacesProvider):
    """Adapter for the existing bounded Overpass implementation."""
    def __init__(self, callback, name="OpenStreetMap Overpass"):
        self.callback, self.name = callback, name

    def search(self, query, location, category=None, radius=3000):
        result = self.callback(query, location, category, radius)
        for place in result.get("results", []):
            loc = place.get("location") or {}
            place.setdefault("lat", loc.get("latitude")); place.setdefault("lon", loc.get("longitude"))
            place.setdefault("website_url", place.get("website"))
            place.setdefault("official_url", None)
            place.setdefault("official_url_status", "unverified")
            place.setdefault("source_confidence", "low")
            place.setdefault("source_type", "community_map")
        result.setdefault("provider", self.name)
        return result


class CallbackPlaceDetailsProvider(PlaceDetailsProvider):
    def __init__(self, callback, name="OpenStreetMap tags"):
        self.callback, self.name = callback, name

    def details(self, place_name, location):
        result = self.callback(place_name, location)
        result.setdefault("category", None)
        result.setdefault("address", (result.get("coordinates") or {}).get("formatted_address"))
        result.setdefault("website_url", result.get("website"))
        result.setdefault("official_url", None)
        result.setdefault("official_url_status", "unverified")
        result.setdefault("recommended_duration", None)
        result.setdefault("nearest_station", None)
        result.setdefault("retrieved_at", result.get("checked_at"))
        result.setdefault("field_status", {key: ("requires_verification" if result.get(key) is None else "community_mapped")
            for key in ("opening_hours", "ticket", "reservation", "nearest_station", "recommended_duration")})
        result.setdefault("provider", self.name)
        return result
