"""Bounded, evidence-gated replanning helpers layered beside decision_loop.

This module does not search the web itself. The Agent/MCP performs each planned
retry and supplies the returned evidence. No booking or other side effect is
available here.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PRIORITY = {"HARD_CONSTRAINT": 4, "SOFT_CONSTRAINT": 3, "PREFERENCE": 2, "OPTIONAL": 1}
ALLOWED_SOURCES = {"USER_SELECTED", "AGENT_SELECTED", "AUTO_SELECTED"}
ALLOWED_CONFIRMATIONS = {"NOT_REQUIRED", "AWAITING_USER", "USER_CONFIRMED"}
MAX_REPLAN_ROUNDS = 3
MAX_SEARCH_ATTEMPTS = 5


def selection_metadata(source: str, confirmation: str | None = None) -> dict:
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"invalid selection_source: {source}")
    if confirmation is None:
        confirmation = "USER_CONFIRMED" if source == "USER_SELECTED" else (
            "NOT_REQUIRED" if source == "AUTO_SELECTED" else "AWAITING_USER")
    if confirmation not in ALLOWED_CONFIRMATIONS:
        raise ValueError(f"invalid confirmation_status: {confirmation}")
    return {"selection_source": source, "confirmation_status": confirmation}


def _profile(data: dict) -> dict:
    return data.get("trip_profile") or data.get("profile") or data


def classify_constraints(profile: dict) -> dict:
    """Classify explicit user constraints; do not elevate preferences by guess."""
    result = {}
    if profile.get("budget_amount") is not None:
        result["budget"] = {"priority": "HARD_CONSTRAINT", "value": profile["budget_amount"],
                             "currency": profile.get("budget_currency"), "basis": profile.get("budget_scope")}
    steps = profile.get("walking_tolerance_steps")
    if isinstance(steps, (int, float)) and steps > 0:
        hard = profile.get("walking_limit_priority", "HARD_CONSTRAINT") == "HARD_CONSTRAINT"
        result["walking"] = {"priority": "HARD_CONSTRAINT" if hard else "SOFT_CONSTRAINT", "value": steps}
    sleep = profile.get("sleep_schedule") or profile.get("start_time_preference")
    if sleep:
        result["sleep"] = {"priority": "SOFT_CONSTRAINT", "value": sleep,
                           "preferred_start": profile.get("preferred_start_time", "09:30")}
    for key in ("interests", "food_preferences", "photography"):
        if profile.get(key):
            result[key] = {"priority": "PREFERENCE", "value": profile[key]}
    for key in ("shopping_level", "optional_activities"):
        if profile.get(key):
            result[key] = {"priority": "OPTIONAL", "value": profile[key]}
    return result


def _minutes(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        return None
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def detect_conflicts(profile: dict, plan: dict) -> list[dict]:
    """Detect supported conflicts from explicit constraints and supplied plan data."""
    constraints = classify_constraints(profile)
    conflicts = []
    budget = constraints.get("budget")
    budget_data = plan.get("budget_state") or plan.get("budget") or {}
    current = budget_data.get("current_plan_cost", budget_data.get("current_total"))
    if current is None and isinstance(budget_data.get("recommended"), dict):
        current = budget_data["recommended"].get("per_person")
    if budget and isinstance(current, (int, float)) and current > budget["value"]:
        conflicts.append({"code": "BUDGET_CONFLICT", "priority": "HARD_CONSTRAINT", "scope": "trip",
                          "current": current, "limit": budget["value"], "gap": round(current-budget["value"], 2),
                          "basis": budget.get("basis"), "resolution_order": ["cheaper_lodging_area", "hotel", "transport", "free_attractions", "food", "destination"]})
    walking = constraints.get("walking")
    sleep = constraints.get("sleep")
    distance_limit = profile.get("daily_distance_limit_km")
    commute_limit = profile.get("max_daily_commute_minutes")
    duration_limit = profile.get("daily_activity_limit_minutes")
    for index, day in enumerate(plan.get("days", []), 1):
        steps = day.get("estimated_steps")
        if walking and isinstance(steps, (int, float)) and steps > walking["value"]:
            conflicts.append({"code": "WALKING_CONFLICT", "priority": walking["priority"], "scope": f"day_{index}",
                              "estimated_steps": steps, "limit_steps": walking["value"], "basis": day.get("steps_basis", "estimated")})
        if isinstance(distance_limit, (int, float)) and isinstance(day.get("distance_km"), (int, float)) and day["distance_km"] > distance_limit:
            conflicts.append({"code": "DISTANCE_CONFLICT", "priority": "HARD_CONSTRAINT", "scope": f"day_{index}",
                              "distance_km": day["distance_km"], "limit_km": distance_limit, "basis": day.get("distance_basis", "estimated")})
        activity_minutes = [item.get("duration_minutes") for item in day.get("activities", []) if isinstance(item.get("duration_minutes"), (int, float))]
        if isinstance(duration_limit, (int, float)) and sum(activity_minutes) > duration_limit:
            conflicts.append({"code": "TIME_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                              "planned_activity_minutes": sum(activity_minutes), "available_minutes": duration_limit})
        if day.get("transport_conflict") is True:
            conflicts.append({"code": "TRANSPORT_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                              "reason": day.get("transport_conflict_reason", "Validated transfer or service-time conflict"),
                              "evidence": day.get("transport_evidence", [])})
        for activity in day.get("activities", []):
            start = _minutes(activity.get("start_time") or activity.get("time"))
            desired = _minutes(sleep.get("preferred_start")) if sleep else None
            if sleep and start is not None and desired is not None and start < desired:
                conflicts.append({"code": "SLEEP_SCHEDULE_CONFLICT", "priority": sleep["priority"], "scope": f"day_{index}",
                                  "activity": activity.get("name") or activity.get("activity"), "start_time": activity.get("start_time") or activity.get("time"),
                                  "preferred_start": sleep.get("preferred_start")})
            close = _minutes(activity.get("closes_at"))
            arrive = _minutes(activity.get("arrival_time"))
            finish = _minutes(activity.get("planned_finish"))
            if close is not None and ((arrive is not None and arrive >= close) or (finish is not None and finish > close)):
                conflicts.append({"code": "OPENING_HOURS_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                                  "activity": activity.get("name"), "closes_at": activity.get("closes_at"),
                                  "arrival_time": activity.get("arrival_time"), "planned_finish": activity.get("planned_finish")})
            if activity.get("reservation_required") is True and activity.get("reservation_status") in {"unavailable", "sold_out", "closed", "required_but_unsecured"}:
                conflicts.append({"code": "RESERVATION_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                                  "activity": activity.get("name"), "reservation_status": activity.get("reservation_status"),
                                  "evidence": activity.get("reservation_evidence", [])})
            if activity.get("weather_sensitive") is True and activity.get("weather_status") in {"unsafe", "severe", "cancelled", "closed_due_to_weather"}:
                conflicts.append({"code": "WEATHER_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                                  "activity": activity.get("name"), "weather_status": activity.get("weather_status"),
                                  "evidence": activity.get("weather_evidence", [])})
            if activity.get("interest_match_score") is not None and activity["interest_match_score"] < profile.get("minimum_interest_match", 0.25):
                conflicts.append({"code": "INTEREST_CONFLICT", "priority": "PREFERENCE", "scope": f"day_{index}",
                                  "activity": activity.get("name"), "interest_match_score": activity["interest_match_score"]})
            if profile.get("avoid_crowds") and activity.get("crowd_level") in {"high", "very_high"}:
                conflicts.append({"code": "CROWD_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": f"day_{index}",
                                  "activity": activity.get("name"), "crowd_level": activity.get("crowd_level"),
                                  "evidence": activity.get("crowd_evidence", [])})
    hotel_commute = (plan.get("hotel") or {}).get("daily_commute_minutes")
    if isinstance(commute_limit, (int, float)) and isinstance(hotel_commute, (int, float)) and hotel_commute > commute_limit:
        conflicts.append({"code": "HOTEL_LOCATION_CONFLICT", "priority": "SOFT_CONSTRAINT", "scope": "lodging",
                          "daily_commute_minutes": hotel_commute, "limit_minutes": commute_limit,
                          "evidence": (plan.get("hotel") or {}).get("commute_evidence", [])})
    for item in plan.get("validated_conflicts", []):
        if isinstance(item, dict) and item.get("code") and item.get("evidence"):
            conflicts.append(dict(item))
    seen, unique = set(), []
    for item in conflicts:
        key = (item.get("code"), item.get("scope"), item.get("activity"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def build_retry_strategy(domain: str, profile: dict) -> dict:
    """Return a finite host-executable research plan, not a claim that it ran."""
    dates = profile.get("travel_window") or profile.get("travel_dates") or "DATE_REQUIRED"
    party = profile.get("traveler_count", "PARTY_REQUIRED")
    if domain in {"hotel", "lodging", "hotels"}:
        raw = [("official", "official property booking pages for target dates, party, and room"),
               ("ota", "trusted OTA exact dates + party + room-type comparison"),
               ("regional_hotel_index", "destination tourism board / official area hotel directory"),
               ("named_property_exact", "candidate property name + target dates + room + party"),
               ("multilingual", "repeat candidate/area query in English and local language")]
    elif domain in {"flight", "flights"}:
        raw = [("airline_official", "origin/destination + exact target dates + party + baggage"),
               ("airport_or_airline_route", "verify operating airports and direct-route operators"),
               ("trusted_flight_search", "exact-date combinations, total journey cost, baggage"),
               ("alternate_airports", "nearby airports only if travel constraints permit; do not assume permission"),
               ("multilingual", "repeat exact-date route query in English and local language")]
    else:
        raise ValueError("retry strategy is defined only for hotels and flights")
    return {"domain": domain, "max_attempts": MAX_SEARCH_ATTEMPTS,
            "attempts": [{"attempt": i, "provider_class": provider, "query": query,
                          "travel_window": dates, "traveler_count": party, "status": "PENDING"}
                         for i, (provider, query) in enumerate(raw, 1)],
            "providers_attempted": [], "failure_reason": None, "search_status": "PENDING",
            "stop_when": ["exact evidence found", "all five attempts exhausted", "user-required date/constraint is missing"],
            "nearby_date_search_allowed": bool(profile.get("date_flexibility")),
            "note": "PENDING means the host Agent must execute and log the search; this plan is not evidence of execution."}


def record_retry_results(strategy: dict, results: list[dict]) -> dict:
    """Attach only actually executed host search attempts to a retry plan."""
    if len(results) > MAX_SEARCH_ATTEMPTS:
        raise ValueError("retry result count exceeds the five-attempt bound")
    attempts = {row["attempt"]: row for row in strategy.get("attempts", [])}
    logged = []
    for item in results:
        index = item.get("attempt")
        if index not in attempts or item.get("executed") is not True or not item.get("provider"):
            raise ValueError("each retry result must match a planned attempt and include executed=true and provider")
        row = {**attempts[index], **item}
        row.pop("executed", None)
        logged.append(row)
    found = any(row.get("exact_quote_status") == "EXACT_DATE_QUOTE" or row.get("status") == "FOUND" for row in logged)
    strategy = dict(strategy)
    strategy["attempts"] = [next((row for row in logged if row["attempt"] == planned["attempt"]), planned)
                            for planned in strategy.get("attempts", [])]
    strategy["providers_attempted"] = list(dict.fromkeys(row["provider"] for row in logged))
    strategy["search_status"] = "FOUND" if found else "UNAVAILABLE" if len(logged) == MAX_SEARCH_ATTEMPTS else "IN_PROGRESS"
    strategy["failure_reason"] = None if found else (logged[-1].get("failure_reason") or "No exact-date evidence was returned." if len(logged) == MAX_SEARCH_ATTEMPTS else None)
    return strategy


def classify_flight_result(*, exact_date_quote=None, nearby_date_reference=None, date_flexibility=False):
    """Do not promote nearby-date examples to a quote or change dates silently."""
    if exact_date_quote:
        return {"status": "EXACT_DATE_QUOTE", "selected": exact_date_quote}
    if nearby_date_reference and date_flexibility:
        return {"status": "NEARBY_DATE_REFERENCE", "selected": nearby_date_reference,
                "note": "Reference only; user-authorized date flexibility is required before changing the plan."}
    if nearby_date_reference:
        return {"status": "UNAVAILABLE", "selected": None,
                "nearby_date_reference": nearby_date_reference,
                "note": "Nearby dates are not a quote for the requested trip and date flexibility is not authorized."}
    return {"status": "UNAVAILABLE", "selected": None}


def budget_status(user_limit=None, current_plan_cost=None, lowest_found_cost=None,
                  realistic_minimum_cost=None, *, evidence_status="unverified", currency=None):
    """Keep a cap, modeled cost, and observed minimum semantically distinct."""
    gap = None if lowest_found_cost is None or user_limit is None else round(max(0, lowest_found_cost-user_limit), 2)
    if evidence_status != "verified" or current_plan_cost is None:
        feasibility = "UNVERIFIED"
    elif current_plan_cost <= user_limit:
        feasibility = "WITHIN_BUDGET"
    else:
        feasibility = "LIKELY_INSUFFICIENT" if lowest_found_cost is None or lowest_found_cost > user_limit else "WITHIN_BUDGET"
    return {"user_budget_limit": user_limit, "current_plan_cost": current_plan_cost,
            "lowest_found_cost": lowest_found_cost, "realistic_minimum_cost": realistic_minimum_cost,
            "budget_gap": gap, "feasibility": feasibility, "currency": currency,
            "evidence_status": evidence_status}


def _valid_evidence(candidate):
    if not isinstance(candidate, dict) or not str(candidate.get("source_url", "")).startswith("https://"):
        return False
    try:
        datetime.fromisoformat(str(candidate.get("checked_at", "")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return bool(candidate.get("id") and candidate.get("name"))


def _utility(candidate, priorities):
    components = candidate.get("utility_components", {})
    total = 0.0
    for factor, score in components.items():
        if not isinstance(score, (int, float)):
            continue
        priority = priorities.get(factor, "PREFERENCE")
        weight = {"HARD_CONSTRAINT": 1000, "SOFT_CONSTRAINT": 4, "PREFERENCE": 2, "OPTIONAL": 0.5}.get(priority, 2)
        total += float(score) * weight
    return total


def replan(profile: dict, initial_plan: dict, candidates_by_decision: dict, *,
           max_rounds=MAX_REPLAN_ROUNDS, min_utility_improvement=0.15):
    """Try sourced alternatives before escalation; stable and bounded by round count."""
    if not 1 <= max_rounds <= MAX_REPLAN_ROUNDS:
        raise ValueError(f"max_rounds must be in 1..{MAX_REPLAN_ROUNDS}")
    constraints = classify_constraints(profile)
    conflicts = detect_conflicts(profile, initial_plan)
    current = json.loads(json.dumps(initial_plan, ensure_ascii=False))
    revision_ledger, escalations = [], {}
    escalation_levels = []
    priorities = {key: item["priority"] for key, item in constraints.items()}
    for round_number in range(1, max_rounds + 1):
        if not conflicts:
            break
        changed = False
        for conflict in conflicts:
            default_decisions = {
                "WALKING_CONFLICT": "route", "SLEEP_SCHEDULE_CONFLICT": "route", "OPENING_HOURS_CONFLICT": "route",
                "DISTANCE_CONFLICT": "route", "TIME_CONFLICT": "route", "WEATHER_CONFLICT": "route",
                "CROWD_CONFLICT": "route", "TRANSPORT_CONFLICT": "route", "BUDGET_CONFLICT": "lodging_area",
                "HOTEL_LOCATION_CONFLICT": "lodging_area", "RESERVATION_CONFLICT": "attractions",
                "INTEREST_CONFLICT": "attractions",
            }
            default_decision = default_decisions.get(conflict["code"], conflict["code"].removesuffix("_CONFLICT").lower())
            decision = conflict.get("decision", default_decision)
            options = [x for x in candidates_by_decision.get(decision, []) if _valid_evidence(x)]
            viable = []
            for option in options:
                hard = option.get("hard_constraints", {})
                if any(value is False for key, value in hard.items() if constraints.get(key, {}).get("priority") == "HARD_CONSTRAINT"):
                    continue
                accepted_tradeoffs = set(option.get("accepted_tradeoffs", []))
                soft = option.get("soft_constraints", {})
                if any(value is False and key not in accepted_tradeoffs for key, value in soft.items()
                       if constraints.get(key, {}).get("priority") == "SOFT_CONSTRAINT"):
                    continue
                step_limit = constraints.get("walking", {}).get("value")
                if step_limit is not None and isinstance(option.get("estimated_steps"), (int, float)) and option["estimated_steps"] > step_limit:
                    continue
                budget_limit = constraints.get("budget", {}).get("value")
                total_cost = option.get("total_trip_cost_per_person")
                if isinstance(budget_limit, (int, float)) and isinstance(total_cost, (int, float)) and total_cost > budget_limit:
                    continue
                start, preferred = _minutes(option.get("start_time")), _minutes(constraints.get("sleep", {}).get("preferred_start"))
                if start is not None and preferred is not None and start < preferred and option.get("soft_tradeoff_accepted") is not True:
                    continue
                viable.append(option)
            if not viable:
                escalation_levels.append(3)
                entry = escalations.setdefault(decision, {"decision": decision, "conflict": conflict, "conflicts": [],
                    "level": 3, "status": "USER_DECISION_REQUIRED",
                    "reason": "No evidence-backed alternative satisfies the applicable constraints."})
                entry["conflicts"].append(conflict)
                continue
            viable.sort(key=lambda option: (-_utility(option, priorities), str(option["id"])))
            best = viable[0]
            near_tie = [item for item in viable[1:] if abs(_utility(best, priorities)-_utility(item, priorities)) < min_utility_improvement]
            escalation_level = 2 if near_tie else 1
            escalation_levels.append(escalation_level)
            old_id = current.get("decisions", {}).get(decision)
            current_candidate = next((x for x in options if x.get("id") == old_id), None)
            improvement = 1.0 if current_candidate is None else _utility(best, priorities) - _utility(current_candidate, priorities)
            material = conflict.get("priority") == "HARD_CONSTRAINT" or improvement >= min_utility_improvement
            if not material or old_id == best["id"]:
                if old_id == best["id"] and revision_ledger and revision_ledger[-1]["decision"] == decision:
                    triggers = revision_ledger[-1].setdefault("triggers", [revision_ledger[-1]["trigger"]])
                    if conflict["code"] not in triggers:
                        triggers.append(conflict["code"])
                        revision_ledger[-1].setdefault("evidence", []).extend(best.get("additional_evidence", []))
                continue
            current.setdefault("decisions", {})[decision] = best["id"]
            current.setdefault("decision_details", {})[decision] = {"name": best["name"], **selection_metadata("AUTO_SELECTED" if profile.get("auto_decision_mode") else "AGENT_SELECTED"),
                "source_url": best["source_url"], "checked_at": best["checked_at"], "confidence": best.get("confidence", "medium")}
            patch = best.get("plan_patch", {})
            if isinstance(patch, dict):
                for key, value in patch.items():
                    current[key] = value
            for key in ("start_time", "estimated_steps", "activities", "route_summary", "cost", "cost_basis"):
                if key in best:
                    current[key] = best[key]
            if "days" in current and "days" not in patch and any(key in best for key in ("start_time", "estimated_steps", "activities")):
                day_index = int(best.get("day_index", 0))
                if 0 <= day_index < len(current["days"]):
                    for key in ("estimated_steps", "start_time", "activities"):
                        if key in best:
                            current["days"][day_index][key] = best[key]
            revision_ledger.append({"revision_id": f"revision-{len(revision_ledger)+1}", "round": round_number,
                "decision": decision, "old_decision": old_id, "new_decision": best["id"],
                "trigger": conflict["code"], "evidence": [best["source_url"]], "checked_at": best["checked_at"],
                "triggers": [conflict["code"]],
                "question_escalation_level": escalation_level,
                "default_recommendation": best["id"],
                "tradeoff_options": [best["id"], *[item["id"] for item in near_tie]],
                "reason": best.get("why_selected", "Evidence-backed alternative better satisfies user constraints."),
                "impact": best.get("impact", {}), "utility_improvement": round(improvement, 4), "material_change": True})
            changed = True
        refreshed = detect_conflicts(profile, current)
        previous_signature = {(item.get("code"), item.get("scope"), item.get("activity")) for item in conflicts}
        refreshed_signature = {(item.get("code"), item.get("scope"), item.get("activity")) for item in refreshed}
        if not changed or refreshed_signature == previous_signature:
            conflicts = refreshed
            break
        conflicts = refreshed
    remaining_signatures = {(item.get("code"), item.get("scope"), item.get("activity")) for item in conflicts}
    escalation_list = [entry for entry in escalations.values()
                       if any((item.get("code"), item.get("scope"), item.get("activity")) in remaining_signatures
                              for item in entry.get("conflicts", []))]
    status = "REPLANNED" if revision_ledger and not conflicts else ("USER_DECISION_REQUIRED" if escalation_list and conflicts else "CONFLICT_UNRESOLVED" if conflicts else "NO_REVISION_NEEDED")
    retry_domains = set()
    if any(item["code"] == "BUDGET_CONFLICT" for item in detect_conflicts(profile, initial_plan)):
        retry_domains.update({"hotels", "flights"})
    bounded_retry_plans = {domain: build_retry_strategy(domain, profile) for domain in sorted(retry_domains)}
    return {"status": status, "constraints": constraints, "initial_plan": initial_plan, "revised_plan": current,
            "conflicts_before": detect_conflicts(profile, initial_plan), "conflicts_after": conflicts,
            "revision_ledger": revision_ledger, "user_decisions": escalation_list[:3],
            "user_decision_count": min(3, len(escalation_list)), "max_rounds": max_rounds,
            "question_escalation_level": max(escalation_levels, default=0),
            "bounded_retry_plans": bounded_retry_plans,
            "side_effects": {"booking": False, "payment": False, "personal_data_submission": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input"); parser.add_argument("--output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = replan(payload["profile"], payload["initial_plan"], payload.get("candidates_by_decision", {}),
                    max_rounds=payload.get("max_rounds", MAX_REPLAN_ROUNDS))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(json.dumps({"status": result["status"], "conflicts_before": len(result["conflicts_before"]),
                      "conflicts_after": len(result["conflicts_after"]), "revisions": len(result["revision_ledger"]),
                      "questions": result["user_decision_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
