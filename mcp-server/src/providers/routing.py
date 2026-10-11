"""OSRM-compatible walking/driving provider adapter (public shared FOSSGIS endpoint)."""


def route_between(origin, destination, mode, *, geocode, get_json, base_url, checked_at):
    if mode not in ("walking", "driving", "transit"):
        raise ValueError("mode must be walking, driving, or transit")
    checked = checked_at()
    if mode == "transit":
        return {"origin": origin, "destination": destination, "mode": mode, "distance": None, "duration": None,
                "route_summary": "No reliable transit timetable provider is configured.", "provider": None,
                "checked_at": checked, "confidence": "low", "status": "unavailable",
                "fallback_strategy": {"kind":"host_search","query":f"official public transit route and timetable from {origin} to {destination}",
                                      "instructions":"Search official transport operators or a host-provided maps tool. Verify service date, transfers, first/last train, fare, and disruptions before presenting a route."},
                "limitations": ["Use host-native maps/search and official operator information; no public-transport duration or fare is fabricated."]}
    a, b = geocode(origin), geocode(destination)
    if not a or not b:
        return {"origin": origin, "destination": destination, "mode": mode, "distance": None, "duration": None, "provider": "Open-Meteo/Nominatim Geocoding", "checked_at": checked, "confidence": "low", "status": "unavailable", "limitations": ["Could not geocode both endpoints."]}
    profile = "routed-foot" if mode == "walking" else "routed-car"
    url = f"{base_url}/{profile}/route/v1/driving/{a[0]['longitude']},{a[0]['latitude']};{b[0]['longitude']},{b[0]['latitude']}?overview=false&alternatives=false&steps=false"
    try:
        result = get_json(url, timeout=12)
    except Exception as exc:
        return {"origin": origin, "destination": destination, "mode": mode, "distance": None, "duration": None, "route_summary": "Routing provider could not be reached; treat route time as unknown.", "provider": "FOSSGIS OSRM / OpenStreetMap", "source": "https://routing.openstreetmap.de/about.html", "checked_at": checked, "confidence": "low", "status": "unavailable", "limitations": [f"{type(exc).__name__}: {str(exc)[:180]}", "Use native maps or geographic clustering; no route time is fabricated."]}
    routes = result.get("routes") or []
    if result.get("code") != "Ok" or not routes:
        return {"origin": origin, "destination": destination, "mode": mode, "distance": None, "duration": None, "route_summary": "Routing provider returned no route.", "provider": "FOSSGIS OSRM / OpenStreetMap", "checked_at": checked, "confidence": "low", "status": "unavailable", "limitations": [result.get("code", "No route")]}
    route = routes[0]
    return {"origin": origin, "destination": destination, "mode": mode, "distance": round(route["distance"]), "duration": round(route["duration"]), "route_summary": f"{mode} route using OpenStreetMap road/path data", "provider": "FOSSGIS OSRM / OpenStreetMap", "source": "https://routing.openstreetmap.de/about.html", "checked_at": checked, "confidence": "medium", "status": "available", "data_status": "estimated", "limitations": ["Shared community routing service; routing is an estimate, not a live traffic or accessible-route guarantee."]}
