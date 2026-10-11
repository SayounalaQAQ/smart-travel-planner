"""Open-Meteo forecast adapter with explicit horizon fallback."""
import datetime as dt
import urllib.parse


def get_weather(location, start, end, *, geocode, registry, get_json, checked_at):
    points = geocode(location)
    if not points:
        return {"status": "unavailable", "reason": "Location could not be geocoded"}
    point = points[0]
    start_date, end_date, today = dt.date.fromisoformat(start), dt.date.fromisoformat(end), dt.date.today()
    if end_date < start_date or (end_date - start_date).days > 16:
        raise ValueError("date_range must be ISO dates and no longer than 17 days")
    if end_date >= today and start_date <= today + dt.timedelta(days=15):
        params = {"latitude": point["latitude"], "longitude": point["longitude"], "start_date": max(start_date, today).isoformat(), "end_date": end_date.isoformat(), "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,wind_speed_10m_max,sunrise,sunset", "timezone": "auto"}
        result = get_json(registry.endpoint("weather") + "?" + urllib.parse.urlencode(params))
        return {"location": point, "forecast_type": "forecast", "daily": result.get("daily", {}), "source": "https://open-meteo.com/", "checked_at": checked_at(), "confidence": "medium"}
    return {"location": point, "forecast_type": "historical_climate_unavailable", "note": "Exact daily forecast is not available this far ahead; use seasonal climate sources and recheck near departure.", "source": "https://open-meteo.com/", "checked_at": checked_at(), "confidence": "low"}
