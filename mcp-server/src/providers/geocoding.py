"""Open-Meteo primary and Nominatim fallback geocoding adapter."""
import urllib.parse


def geocode(name, region="", *, registry, get_json):
    query = ", ".join(x for x in (name, region) if x)
    url = registry.endpoint("geocoding") + "?" + urllib.parse.urlencode({"name": query, "count": 5, "language": "en", "format": "json"})
    primary_error = None
    try:
        results = get_json(url)
    except Exception as exc:
        primary_error = exc
        results = {}
    rows = [{"latitude": x["latitude"], "longitude": x["longitude"], "formatted_address": ", ".join(filter(None, [x.get("name"), x.get("admin1"), x.get("country")])), "country": x.get("country"), "region": x.get("admin1"), "city": x.get("name"), "provider": "Open-Meteo Geocoding"} for x in results.get("results", [])]
    if rows:
        return rows
    fallback = registry.endpoint("geocoding", fallback=True)
    try:
        data = get_json(fallback + "?" + urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 1}), timeout=8)
    except Exception:
        if primary_error:
            return []
        raise
    out = []
    for item in data if isinstance(data, list) else []:
        address = item.get("address", {})
        out.append({"latitude": float(item["lat"]), "longitude": float(item["lon"]), "formatted_address": item.get("display_name", query), "country": address.get("country"), "region": address.get("state") or address.get("region"), "city": address.get("city") or address.get("town") or address.get("village"), "provider": "Nominatim / OpenStreetMap"})
    return out
