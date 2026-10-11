"""Conservative evidence freshness; timestamps are UTC, not inferred from labels."""
from datetime import datetime, timedelta, timezone

POLICY_HOURS = {"flight_quote": 6, "hotel_quote": 12, "exchange": 24,
                "train_timetable": 168, "route": 168, "weather_forecast": 6,
                "attraction_static": 720, "historical_climate": 8760}


def timestamp(value):
    if not value:
        raise ValueError("missing timestamp")
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def freshness(record, kind, *, now=None):
    now = timestamp(now) if isinstance(now, str) else now or datetime.now(timezone.utc)
    checked = record.get("checked_at") or record.get("retrieved_at")
    valid_until = None
    reason = None
    try:
        checked_time = timestamp(checked)
        if checked_time > now + timedelta(minutes=5):
            raise ValueError("timestamp is in the future")
        # A provider's earlier expiry wins; a long supplied expiry cannot extend policy.
        expires = checked_time + timedelta(hours=POLICY_HOURS[kind])
        if record.get("valid_until"):
            expires = min(expires, timestamp(record["valid_until"]))
        valid_until = expires.isoformat(timespec="seconds")
        refresh = now >= expires
        reason = "EXPIRED" if refresh else None
    except (ValueError, KeyError, TypeError):
        refresh, reason = True, "TIMESTAMP_MISSING_OR_INVALID"
    return {"checked_at": checked, "valid_until": valid_until,
            "freshness_class": kind, "refresh_required": refresh,
            "refresh_reason": reason}
