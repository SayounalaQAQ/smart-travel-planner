"""Real-world readiness records and deterministic plan QA for V0.9.

This module never upgrades a reference or estimate into a live booking quote.
It validates supplied evidence and returns explicit pending states when evidence
is missing.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import re
from typing import Any

HOTEL_PRICE_TYPES = {"EXACT_DATE_PRICE", "DATE_RANGE_REFERENCE", "MONTHLY_REFERENCE", "UNAVAILABLE"}
FLIGHT_TYPES = {"EXACT_DATE_QUOTE", "NEARBY_DATE_REFERENCE", "CURRENT_REFERENCE", "UNAVAILABLE"}
TRANSIT_STATUSES = {"VERIFIED", "ESTIMATED", "CURRENT_REFERENCE", "UNAVAILABLE", "NO_ROUTE_FOUND"}
PLAN_STATUSES = {"PROVISIONAL", "OPTIMIZED", "READY_FOR_CONFIRMATION", "READY_FOR_BOOKING", "DATA_PENDING"}


def _stamp(value: str | None = None) -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def hotel_availability_record(*, hotel_name: str, area: str, room_type: str | None,
                              guest_count: int, check_in: str, check_out: str,
                              currency: str | None = None, total_price: float | None = None,
                              tax_included: bool | None = None, breakfast: str | None = None,
                              cancellation_policy: str | None = None, availability: str = "UNKNOWN",
                              source_url: str | None = None, retrieved_at: str | None = None,
                              confidence: str = "low", price_type: str = "UNAVAILABLE") -> dict[str, Any]:
    """Create and validate a date-scoped hotel record; no generic rate promotion."""
    if guest_count < 1:
        raise ValueError("guest_count must be positive")
    start, end = date.fromisoformat(check_in), date.fromisoformat(check_out)
    if end <= start:
        raise ValueError("check_out must be after check_in")
    if price_type not in HOTEL_PRICE_TYPES:
        raise ValueError(f"Unsupported hotel price_type: {price_type}")
    if price_type == "EXACT_DATE_PRICE":
        if total_price is None or not currency or not room_type or not source_url:
            raise ValueError("Exact-date hotel price requires total_price, currency, room_type and source_url")
        if availability not in {"AVAILABLE", "SOLD_OUT"}:
            raise ValueError("Exact-date price requires explicit availability")
    elif total_price is not None and price_type in {"DATE_RANGE_REFERENCE", "MONTHLY_REFERENCE"}:
        # A reference may carry a price, but must never imply target-date stock.
        if availability == "AVAILABLE":
            raise ValueError("Reference prices cannot assert target-date availability")
    return {
        "hotel_name": hotel_name, "area": area, "room_type": room_type,
        "guest_count": guest_count, "check_in": check_in, "check_out": check_out,
        "currency": currency, "total_price": total_price, "tax_included": tax_included,
        "breakfast": breakfast, "cancellation_policy": cancellation_policy,
        "availability": availability, "source_url": source_url,
        "retrieved_at": _stamp(retrieved_at), "confidence": confidence,
        "price_type": price_type,
    }


def flight_candidate(*, origin_airport: str | None, destination_airport: str | None,
                     flight_date: str, departure_time: str | None = None,
                     arrival_time: str | None = None, airline: str | None = None,
                     flight_number: str | None = None, baggage: str | None = None,
                     price: float | None = None, currency: str | None = None,
                     source: str | None = None, retrieved_at: str | None = None,
                     confidence: str = "low", status: str = "UNAVAILABLE",
                     date_flexibility_authorized: bool = False) -> dict[str, Any]:
    if status not in FLIGHT_TYPES:
        raise ValueError(f"Unsupported flight status: {status}")
    date.fromisoformat(flight_date)
    if status == "EXACT_DATE_QUOTE" and not all((origin_airport, destination_airport, departure_time, arrival_time, airline, price is not None, currency, source)):
        raise ValueError("Exact-date flight quote requires airports, times, airline, price, currency and source")
    if status == "NEARBY_DATE_REFERENCE" and not date_flexibility_authorized:
        raise ValueError("Nearby-date reference cannot be selected without explicit date-flexibility authorization")
    return {"origin_airport": origin_airport, "destination_airport": destination_airport,
            "flight_date": flight_date, "departure_time": departure_time, "arrival_time": arrival_time,
            "airline": airline, "flight_number": flight_number, "baggage": baggage,
            "price": price, "currency": currency, "source": source,
            "retrieved_at": _stamp(retrieved_at), "confidence": confidence, "status": status}


def station_route(*, from_station: str, to_station: str, operator: str | None = None,
                  line: str | None = None, transfer: list[str] | None = None,
                  duration_minutes: int | None = None, fare: float | None = None,
                  currency: str | None = None, walking_minutes: int | None = None,
                  source: str | None = None, status: str = "UNAVAILABLE",
                  checked_at: str | None = None) -> dict[str, Any]:
    if status not in TRANSIT_STATUSES:
        raise ValueError(f"Unsupported transit status: {status}")
    if status == "VERIFIED" and not all((operator, line, duration_minutes is not None, fare is not None, source)):
        raise ValueError("VERIFIED transit requires operator, line, duration, fare and source")
    if status == "ESTIMATED" and not source:
        raise ValueError("ESTIMATED transit still requires a source or explicit basis")
    return {"from": from_station, "to": to_station, "operator": operator, "line": line,
            "transfer": transfer or [], "duration_minutes": duration_minutes, "fare": fare,
            "currency": currency, "walking_minutes": walking_minutes, "source": source,
            "status": status, "checked_at": _stamp(checked_at)}


def bounded_hotel_search_plan(hotel_name: str, *, max_attempts: int = 4) -> dict[str, Any]:
    if not 1 <= max_attempts <= 5:
        raise ValueError("hotel retry limit must be between 1 and 5")
    providers = ["hotel_official", "official_tourism", "ota", "reliable_hotel_page", "multilingual_exact_dates"]
    return {"hotel_name": hotel_name, "max_attempts": max_attempts,
            "attempts": [{"attempt": i + 1, "provider": providers[i], "status": "PENDING"}
                         for i in range(max_attempts)],
            "providers_attempted": [], "attempt_count": 0,
            "failure_reason": None, "best_available_result": None}


def record_hotel_search(plan: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    if len(results) > plan["max_attempts"]:
        raise ValueError("hotel search exceeded bounded attempt count")
    out = deepcopy(plan)
    for expected, result in zip(out["attempts"], results):
        if result.get("attempt") != expected["attempt"] or result.get("provider") != expected["provider"]:
            raise ValueError("retry result does not match planned provider sequence")
        if result.get("executed") is not True:
            raise ValueError("attempt must be explicitly marked executed")
        expected.update({"status": result.get("status", "NO_EXACT_DATE_RESULT"),
                         "failure_reason": result.get("failure_reason"),
                         "source_url": result.get("source_url"), "retrieved_at": result.get("retrieved_at")})
    out["attempt_count"] = len(results)
    out["providers_attempted"] = [row["provider"] for row in results]
    out["failure_reason"] = next((r.get("failure_reason") for r in reversed(results) if r.get("failure_reason")), None)
    out["best_available_result"] = next((r.get("record") for r in results if r.get("record")), None)
    return out


HOTEL_FIT_WEIGHTS = {"price": .24, "location": .18, "station_distance": .10,
    "airport_access": .10, "kyoto_access": .08, "food_access": .08,
    "night_access": .06, "breakfast": .04, "cancellation": .06, "user_fit": .06}


def rank_hotel_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank only evidence-backed fit values; unknown target-date prices never score as cheap."""
    rows = []
    exact_prices = [float(row["total_price"]) for row in candidates
                   if row.get("price_type") == "EXACT_DATE_PRICE" and row.get("total_price") is not None
                   and row.get("availability") == "AVAILABLE"]
    low, high = (min(exact_prices), max(exact_prices)) if exact_prices else (None, None)
    for candidate in candidates:
        parts = {}
        for key, weight in HOTEL_FIT_WEIGHTS.items():
            value = candidate.get("fit", {}).get(key)
            if key == "price":
                price = candidate.get("total_price")
                exact_available_rate = candidate.get("price_type") == "EXACT_DATE_PRICE" and candidate.get("availability") == "AVAILABLE"
                value = (1.0 if high == low else 1 - (float(price)-low)/(high-low)) if exact_available_rate and price is not None and low is not None else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
                parts[key] = round(float(value) * weight, 4)
        coverage = sum(HOTEL_FIT_WEIGHTS[key] for key in parts)
        score = round(sum(parts.values()) / coverage, 4) if coverage else None
        convenience_keys = ("location", "station_distance", "airport_access", "kyoto_access", "food_access", "night_access")
        convenience_values = [candidate.get("fit", {}).get(key) for key in convenience_keys
                              if isinstance(candidate.get("fit", {}).get(key), (int, float))]
        convenience_score = round(sum(convenience_values) / len(convenience_values), 4) if convenience_values else None
        rows.append({"hotel_name": candidate.get("hotel_name") or candidate.get("name"),
                     "score": score, "evidence_coverage": round(coverage, 4),
                     "convenience_score": convenience_score,
                     "availability": candidate.get("availability", "UNKNOWN"),
                     "price_type": candidate.get("price_type", "UNAVAILABLE"),
                     "selection_source": "AUTO_SELECTED" if score is not None else None,
                     "why_selected": candidate.get("why_selected") if score is not None else None})
    ranked = sorted((r for r in rows if r["score"] is not None), key=lambda r:(-r["score"], r["hotel_name"] or ""))
    exact_available = [r for r in ranked if r["availability"] == "AVAILABLE" and r["price_type"] == "EXACT_DATE_PRICE"]
    if not exact_available:
        return {"status": "DATA_PENDING", "candidates": rows,
                "picks": {"budget_pick": None, "best_value": None, "best_convenience": None},
                "reason": "目标日期库存/总价不足，不能声称某家是预算或性价比优选。"}
    return {"status": "RANKED", "candidates": rows,
            "picks": {"budget_pick": min(exact_available, key=lambda r: next(float(c["total_price"]) for c in candidates if (c.get("hotel_name") or c.get("name")) == r["hotel_name"])),
                      "best_value": max(exact_available, key=lambda r:r["score"]),
                      "best_convenience": max(exact_available, key=lambda r:r["convenience_score"] if r["convenience_score"] is not None else -1)} }


def rank_flight_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare baggage, clock, access and elapsed time without inferring missing values."""
    exact = [row for row in candidates if row.get("status") == "EXACT_DATE_QUOTE"]
    if not exact:
        return {"status": "DATA_PENDING", "candidates": candidates,
                "picks": {"cheapest": None, "best_time": None, "best_overall": None}}
    cheapest = min(exact, key=lambda r: r["price"])
    def time_score(row):
        return row.get("departure_comfort_score", 0) + row.get("total_travel_time_score", 0) + row.get("airport_access_score", 0) + row.get("day_impact_score", 0)
    best_time = max(exact, key=time_score)
    best_overall = max(exact, key=lambda r: r.get("overall_score", time_score(r)))
    return {"status": "RANKED", "candidates": candidates,
            "picks": {"cheapest": cheapest, "best_time": best_time, "best_overall": best_overall}}


def detect_diversity_conflicts(days: list[dict[str, Any]], attractions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Flag duplicate attractions/areas unless the traveler explicitly requested repeats."""
    seen: dict[str, tuple[int, str]] = {}
    seen_restaurants: dict[str, int] = {}
    conflicts = []
    attraction_names = [str(row.get("name")) for row in attractions or [] if isinstance(row, dict) and row.get("name")]
    for day_index, day in enumerate(days, 1):
        values = day.get("activities", [])
        for item in values:
            if isinstance(item, dict):
                name = str(item.get("attraction_id") or item.get("attraction") or item.get("activity") or item.get("name") or "").strip()
                repeat = item.get("repeat_requested") is True or day.get("repeat_requested") is True
            else:
                name, repeat = str(item).strip(), day.get("repeat_requested") is True
            canonical = next((known for known in attraction_names if known.casefold() in name.casefold()), None)
            key = " ".join((canonical or name).casefold().split())
            if not key:
                continue
            routine = isinstance(item,dict) and item.get('node_role') in {'MEAL','REST'}
            if key in seen and not repeat and not routine:
                conflicts.append({"code": "DUPLICATE_ACTIVITY", "name": name,
                                  "first_day": seen[key][0], "repeat_day": day_index,
                                  "reason": "相同活动重复出现，且没有用户要求重复的标记。"})
            elif key not in seen and not routine:
                seen[key] = (day_index, name)
            restaurant = item.get("restaurant") if isinstance(item, dict) else None
            if restaurant:
                restaurant_key = " ".join(str(restaurant).casefold().split())
                if restaurant_key in seen_restaurants and item.get("repeat_requested") is not True:
                    conflicts.append({"code": "DUPLICATE_RESTAURANT", "restaurant": restaurant,
                                      "first_day": seen_restaurants[restaurant_key], "repeat_day": day_index})
                else:
                    seen_restaurants[restaurant_key] = day_index
    area_days: dict[str, int] = {}
    for index, day in enumerate(days, 1):
        area = str(day.get("area") or "").strip().casefold()
        if area and area in area_days and day.get("duplicate_area_justified") is not True:
            conflicts.append({"code": "DUPLICATE_AREA", "area": day.get("area"),
                              "first_day": area_days[area], "repeat_day": index,
                              "reason": "区域重复，需要确认是刻意留白/分段遊览还是应改选。"})
        elif area:
            area_days[area] = index
    previous_experience = None
    for index, day in enumerate(days, 1):
        experience = day.get("experience_type")
        if experience and experience == previous_experience and day.get("repeat_requested") is not True:
            conflicts.append({"code": "REPETITIVE_EXPERIENCE", "experience_type": experience,
                              "repeat_day": index, "reason": "相邻日期体验类型重复，需重新检查多样性。"})
        previous_experience = experience
    return conflicts


def validate_route_chain(day: dict[str, Any]) -> list[dict[str, Any]]:
    chain = day.get("route_chain")
    if not chain:
        return [{"code": "ROUTE_COMPLETENESS_CONFLICT", "day": day.get("date"),
                 "reason": "缺少可核验的站到站 route_chain；仅有区域级路线描述。"}]
    issues = []
    nodes = [str(chain[0].get("from", ""))]
    for leg in chain:
        start, end = str(leg.get("from", "")), str(leg.get("to", ""))
        if not start or not end:
            issues.append({"code": "ROUTE_COMPLETENESS_CONFLICT", "reason": "route segment has an empty endpoint"})
        if nodes[-1] and start and nodes[-1].casefold() != start.casefold():
            issues.append({"code": "ROUTE_COMPLETENESS_CONFLICT", "reason": f"route break: {nodes[-1]} → {start}"})
        nodes.append(end)
        if leg.get("status") not in TRANSIT_STATUSES:
            issues.append({"code": "ROUTE_COMPLETENESS_CONFLICT", "reason": f"unknown transit status for {start} → {end}"})
        if leg.get("status") == "VERIFIED" and not leg.get("source"):
            issues.append({"code": "ROUTE_COMPLETENESS_CONFLICT", "reason": f"missing source for {start} → {end}"})
    sequence = day.get("route_sequence")
    if sequence is not None:
        required = ["START", "ACTIVITY", "TRANSIT", "ACTIVITY", "MEAL", "TRANSIT", "RETURN"]
        actual = [str(step.get("type", "")).upper() for step in sequence if isinstance(step, dict)]
        cursor = 0
        for kind in actual:
            if cursor < len(required) and kind == required[cursor]:
                cursor += 1
        if cursor < len(required):
            issues.append({"code": "ROUTE_COMPLETENESS_CONFLICT", "day": day.get("date"),
                           "reason": f"route sequence missing ordered stage {required[cursor]}"})
    return issues


def legacy_plan_qa(plan: dict[str, Any]) -> dict[str, Any]:
    """Run final deterministic QA without pretending missing data is complete."""
    profile = plan.get("trip_profile") or {}
    days = plan.get("days") or []
    findings: list[dict[str, Any]] = []
    diversity = detect_diversity_conflicts(days, plan.get("attractions"))
    findings.extend(diversity)
    if diversity:
        findings.append({"code": "DIVERSITY_CONFLICT", "reason": "重复活动/区域或体验类型会降低行程多样性。", "details": diversity})
    if (plan.get("budget_status") or {}).get("feasibility") in {"LIKELY_INSUFFICIENT", "OVER_LIMIT"}:
        findings.append({"code": "BUDGET_CONFLICT", "reason": "预算证据显示当前方案超过用户上限。"})
    for day in days:
        findings.extend(validate_route_chain(day))
        if day.get("transport_conflict") is True:
            findings.append({"code": "TRANSPORT_CONFLICT", "day": day.get("date"), "reason": "行程记录标记交通冲突。"})
        if day.get("weather_status") in {"unsafe", "closed", "cancelled"}:
            findings.append({"code": "WEATHER_CONFLICT", "day": day.get("date"), "reason": "天气或运营状态不支持该日户外安排。"})
        cap = profile.get("walking_tolerance_steps")
        steps = day.get("estimated_steps")
        if isinstance(cap, (int, float)) and isinstance(steps, (int, float)) and steps > cap:
            findings.append({"code": "WALKING_CONFLICT", "day": day.get("date"), "steps": steps, "cap": cap})
        for activity in day.get("activities", []):
            if not isinstance(activity, dict):
                continue
            if activity.get("planned_finish") and activity.get("closes_at"):
                if activity["planned_finish"] > activity["closes_at"]:
                    findings.append({"code": "OPENING_HOURS_CONFLICT", "day": day.get("date"), "activity": activity.get("activity")})
            if activity.get("reservation_required") is True and activity.get("reservation_status") in {None, "unknown", "UNAVAILABLE"}:
                findings.append({"code": "RESERVATION_CONFLICT", "day": day.get("date"), "activity": activity.get("activity")})
            preferred = str(profile.get("preferred_start_time") or "")
            match = re.search(r"(?<!\d)(\d{1,2}:\d{2})", str(activity.get("time") or ""))
            if preferred and match and match.group(1) < preferred:
                findings.append({"code": "SLEEP_SCHEDULE_CONFLICT", "day": day.get("date"),
                                 "activity": activity.get("activity"), "reason": f"计划开始 {match.group(1)}，早于偏好 {preferred}"})
    hotel_records = plan.get("hotel_availability", [])
    flight_records = plan.get("flight_availability", [])
    date_window = (profile.get("start_date"), profile.get("end_date"))
    has_route = bool(days) and all(day.get("route_chain") and day.get("route_sequence") for day in days)
    route_legs = [leg for day in days for leg in day.get("route_chain", [])]
    if date_window[0] and date_window[1]:
        try:
            span = (date.fromisoformat(date_window[1]) - date.fromisoformat(date_window[0])).days + 1
            if span <= 0 or (profile.get("duration_days") and span != profile.get("duration_days")):
                findings.append({"code": "DATE_LOGIC_CONFLICT", "reason": "起止日期、出行天数不一致。"})
        except ValueError:
            findings.append({"code": "DATE_LOGIC_CONFLICT", "reason": "日期不是有效 ISO 日期。"})
    exact_hotel = any(r.get("price_type") == "EXACT_DATE_PRICE" and r.get("availability") == "AVAILABLE"
                      and (not date_window[0] or r.get("check_in") == date_window[0])
                      and (not date_window[1] or r.get("check_out") == date_window[1]) for r in hotel_records)
    exact_dates = {r.get("flight_date") for r in flight_records if r.get("status") == "EXACT_DATE_QUOTE"}
    exact_flight = (bool(date_window[0] and date_window[1] and {date_window[0], date_window[1]} <= exact_dates)
                    if date_window[0] and date_window[1] else len(exact_dates) >= 1)
    all_transit_verified = bool(route_legs) and has_route and all(x.get("status") == "VERIFIED" for x in route_legs)
    data_status = "VERIFIED" if exact_hotel and exact_flight and all_transit_verified else ("PARTIALLY_UNAVAILABLE" if hotel_records or flight_records else "DATA_PENDING")
    route_status = "COMPLETE" if days and not any(f["code"] == "ROUTE_COMPLETENESS_CONFLICT" for f in findings) else "INCOMPLETE"
    qa_status = "PASS" if not findings else "REPLANNING_REQUIRED"
    if not exact_hotel or not exact_flight or not all_transit_verified:
        travel_readiness = "READY_WITH_PENDING_DATA" if days and route_status == "COMPLETE" and qa_status == "PASS" else "NOT_READY"
        plan_status = "OPTIMIZED" if days else "PROVISIONAL"
        booking_readiness = "NOT_READY"
    else:
        travel_readiness = "READY" if route_status == "COMPLETE" and not findings else "NOT_READY"
        plan_status = "READY_FOR_BOOKING" if travel_readiness == "READY" else "OPTIMIZED"
        booking_readiness = "READY" if travel_readiness == "READY" else "NOT_READY"
    readiness = {"plan_status": plan_status, "data_status": data_status,
                 "booking_readiness": booking_readiness, "travel_plan_readiness": travel_readiness,
                 "route_completeness": route_status, "plan_qa": qa_status,
                 "exact_date_hotel_quote": "VERIFIED" if exact_hotel else "UNAVAILABLE",
                 "exact_date_flight_quote": "VERIFIED" if exact_flight else "UNAVAILABLE"}
    checks = [
        {"check": "user_preferences", "status": "FAIL" if any(x["code"] == "SLEEP_SCHEDULE_CONFLICT" for x in findings) else "PASS"},
        {"check": "hard_constraints_and_walking", "status": "FAIL" if any(x["code"] in {"WALKING_CONFLICT", "BUDGET_CONFLICT"} for x in findings) else "PASS"},
        {"check": "budget_evidence", "status": (plan.get("budget_status") or {}).get("feasibility", "UNVERIFIED")},
        {"check": "fatigue_and_step_estimate", "status": "ESTIMATED" if any(day.get("estimated_steps") is None for day in days) else "ESTIMATED"},
        {"check": "opening_hours", "status": "FAIL" if any(x["code"] == "OPENING_HOURS_CONFLICT" for x in findings) else "PASS"},
        {"check": "reservation", "status": "FAIL" if any(x["code"] == "RESERVATION_CONFLICT" for x in findings) else "PASS"},
        {"check": "transport", "status": "VERIFIED" if all_transit_verified else "UNAVAILABLE_OR_ESTIMATED"},
        {"check": "geographic_clustering", "status": "ESTIMATED" if days else "UNAVAILABLE"},
        {"check": "weather", "status": str(plan.get("weather_data_status") or "HISTORICAL / FORECAST_PENDING")},
        {"check": "attraction_diversity", "status": "FAIL" if any(x["code"] in {"DUPLICATE_ACTIVITY", "DUPLICATE_AREA", "DIVERSITY_CONFLICT", "REPETITIVE_EXPERIENCE"} for x in findings) else "PASS"},
        {"check": "restaurant_diversity", "status": "FAIL" if any(x["code"] == "DUPLICATE_RESTAURANT" for x in findings) else "PASS"},
        {"check": "date_logic", "status": "FAIL" if any(x["code"] == "DATE_LOGIC_CONFLICT" for x in findings) else ("VERIFIED" if date_window[0] and date_window[1] else "UNAVAILABLE")},
        {"check": "arrival_departure", "status": "VERIFIED" if exact_flight else "UNAVAILABLE"},
        {"check": "lodging_location", "status": "AREA_ONLY" if not exact_hotel else "VERIFIED"},
        {"check": "flight_impact", "status": "VERIFIED" if exact_flight else "UNAVAILABLE"},
        {"check": "route_structure", "status": route_status},
    ]
    return {"status": qa_status, "findings": findings, "readiness": readiness,
            "checks": checks,
            "data_completeness_matrix": build_data_completeness_matrix(plan, exact_hotel=exact_hotel, exact_flight=exact_flight)}


def build_data_completeness_matrix(plan: dict[str, Any], *, exact_hotel: bool | None = None,
                                   exact_flight: bool | None = None) -> list[dict[str, str]]:
    profile = plan.get("trip_profile") or {}
    if exact_hotel is None:
        exact_hotel = any(row.get("price_type") == "EXACT_DATE_PRICE" and row.get("availability") == "AVAILABLE" for row in plan.get("hotel_availability", []))
    if exact_flight is None:
        exact_flight = any(row.get("status") == "EXACT_DATE_QUOTE" for row in plan.get("flight_availability", []))
    has_route = bool(plan.get("days")) and all(day.get("route_chain") and day.get("route_sequence") for day in plan.get("days", []))
    route_legs = [leg for day in plan.get("days", []) for leg in day.get("route_chain", [])]
    has_sources = bool(plan.get("sources") or plan.get("decision_ledger"))
    return [
        {"data": "日期", "status": "VERIFIED" if profile.get("start_date") and profile.get("end_date") else "UNAVAILABLE"},
        {"data": "目的地", "status": "VERIFIED" if profile.get("destination_resolved") else "ESTIMATED"},
        {"data": "住宿区域", "status": "VERIFIED" if profile.get("lodging_area") else "ESTIMATED"},
        {"data": "具体酒店/目标日期库存价格", "status": "VERIFIED" if exact_hotel else "UNAVAILABLE"},
        {"data": "目标日期航班报价", "status": "VERIFIED" if exact_flight else "UNAVAILABLE"},
        {"data": "景点及运营信息", "status": "PARTIALLY_VERIFIED" if plan.get("attractions") else "UNAVAILABLE"},
        {"data": "站到站交通链", "status": ("UNAVAILABLE" if not has_route else ("PARTIALLY_UNAVAILABLE" if any(x.get("status") == "UNAVAILABLE" for x in route_legs) else ("ESTIMATED" if any(x.get("status") == "ESTIMATED" for x in route_legs) else "VERIFIED")))},
        {"data": "预算成本证据", "status": "VERIFIED" if (plan.get("budget_status") or {}).get("current_verified_cost") is not None else "UNVERIFIED"},
        {"data": "天气", "status": str(plan.get("weather_data_status") or "HISTORICAL / FORECAST_PENDING")},
        {"data": "票价", "status": "CURRENT / REFERENCE; recheck before travel"},
        {"data": "图片", "status": "VERIFIED" if any(i.get("local_path") or i.get("image_url") for i in plan.get("images", []) if isinstance(i, dict)) else "UNAVAILABLE"},
        {"data": "来源", "status": "VERIFIED" if has_sources else "UNAVAILABLE"},
    ]


def apply_readiness(plan: dict[str, Any]) -> dict[str, Any]:
    from execution_readiness import evaluate_plan
    return evaluate_plan(plan)


def plan_qa(plan: dict[str, Any]) -> dict[str, Any]:
    """Public QA now includes execution, monetary, and state closure."""
    return apply_readiness(plan)["plan_qa"]

