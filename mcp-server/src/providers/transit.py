"""Public-transport provider contract. No timetable is synthesized by fallback."""
from abc import ABC, abstractmethod


class TransitProvider(ABC):
    name = "transit-provider"

    @abstractmethod
    def route(self, origin, destination, *, service_date=None):
        raise NotImplementedError


class UnavailableTransitProvider(TransitProvider):
    name = "no-structured-transit-provider"

    def route(self, origin, destination, *, service_date=None):
        return {"origin": origin, "destination": destination, "mode": "transit", "service_date": service_date, "status": "unavailable",
                "data_status": "unavailable", "duration": None, "fare": None, "transfers": None,
                "walking_segments": None, "provider": None, "checked_at": None, "confidence": "low",
                "fallback_strategy": {"kind": "host_search", "query": f"official transit route {origin} to {destination}",
                    "instructions": "Verify operator route, service date, transfers, fare and first/last service from official sources."},
                "limitations": ["No reliable structured transit provider is configured; route, duration and fare are unavailable."]}


def route_between(origin, destination, mode, walking_driving, transit_provider=None, service_date=None):
    if mode == "transit":
        return (transit_provider or UnavailableTransitProvider()).route(origin, destination, service_date=service_date)
    return walking_driving(origin, destination, mode)
