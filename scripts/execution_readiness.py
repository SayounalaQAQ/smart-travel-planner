"""V0.9.1 route/cost/state closure overlay on the existing decision architecture."""
from copy import deepcopy
from datetime import datetime, timezone
from cost_ledger import reconcile_budget, validate_quote
from data_freshness import freshness
from execution_graph import build_execution_graph, project_graph, route_closure, route_retry_plan
from state_consistency import sync_profile, validate_state


def selected_quote(plan, kind, *, now=None):
    profile = plan["trip_profile"]
    key = profile.get(f"{kind}_quote_id")
    records = plan.get("hotel_availability" if kind == "hotel" else "flight_availability", [])
    candidate = next((r for r in records if key and r.get("quote_id") == key), None)
    if candidate is None:
        return {"status": "UNAVAILABLE", "issues": [f"EXACT_{kind.upper()}_QUOTE_MISSING"],
                "refresh_required": True, "valid_until": None, "checked_at": None,
                "freshness_class": f"{kind}_quote"}
    return {**validate_quote(candidate, kind, profile, now=now), "quote_id": key}


def evaluate_plan(plan, *, now=None, synchronize=True):
    # Local import breaks the compatibility-module import cycle.
    from travel_readiness import legacy_plan_qa
    input_consistency = validate_state(plan, check_readiness=False)
    out = sync_profile(plan) if synchronize else deepcopy(plan)
    profile = out.setdefault("trip_profile", {})
    rail = profile.get('intercity_mode') == 'TRAIN'
    out["quote_validation"] = {kind: selected_quote(out, kind, now=now) for kind in ("hotel", "flight")}
    if rail:
        out['quote_validation']['flight'] = {'status':'NOT_APPLICABLE', 'refresh_required':False, 'issues':[]}
    flight_quote = next((r for r in out.get("flight_availability", []) if r.get("quote_id") == profile.get("flight_quote_id")), {})
    previous_night=None
    for index, day in enumerate(out.get("days", [])):
        day["execution_graph"] = build_execution_graph(profile, day, index,previous_night)
        previous_night=day.get('overnight_anchor')
        for edge in day['execution_graph']['edges']:
            if edge.get('mode') == 'FLIGHT' and edge.get('status') == 'VERIFIED':
                direction = 'OUTBOUND' if day.get('date') == profile.get('start_date') else 'RETURN'
                legs = [r for r in flight_quote.get('legs', []) if r.get('direction') == direction]
                if (out['quote_validation']['flight']['status'] != 'VERIFIED' or
                    edge.get('quote_id') != profile.get('flight_quote_id') or not legs or
                    edge.get('departure_time') != legs[0].get('departure_time') or
                    edge.get('arrival_time') != legs[-1].get('arrival_time')):
                    edge.update(status='UNAVAILABLE', failure_reason='Flight edge does not match selected exact-date round-trip quote', duration_minutes=None)
        project_graph(day)
        day["route_closure"] = route_closure(day["execution_graph"], now=now)
        day["route_research_pending"] = route_retry_plan(day["execution_graph"])
    closure_days = [day["route_closure"] for day in out.get("days", [])]
    required = sum(d["required_edges"] for d in closure_days)
    resolved = sum(d["resolved_edges"] for d in closure_days)
    verified = sum(d["verified_edges"] for d in closure_days)
    route_structure = "COMPLETE" if closure_days and all(d["route_structure_status"] == "COMPLETE" for d in closure_days) else "INCOMPLETE"
    route_verification = "EXECUTION_VERIFIED" if required and verified == required and route_structure == "COMPLETE" else "PARTIAL" if resolved else "UNAVAILABLE"
    out["route_closure"] = {"route_structure_status": route_structure, "required_edges": required,
                            "resolved_edges": resolved, "verified_edges": verified,
                            "route_coverage": round(resolved/required, 4) if required else 0.0,
                            "route_verification_status": route_verification,
                            "daily": [{"date": d.get("date"), **d["route_closure"]} for d in out.get("days", [])]}
    all_quotes = {r["quote_id"]: r for field in ("hotel_availability", "flight_availability") for r in out.get(field, []) if r.get("quote_id")}
    if "cost_ledger" not in out:
        # Legacy allocations are user caps, not prices; never import them as cost.
        out["cost_ledger"] = [{"id": f"missing-{category}", "category": category, "item": "尚未获得成本证据",
            "amount": None, "currency": profile.get("budget_currency"), "scope": "PER_PARTY",
            "traveler_count": profile.get("traveler_count"), "quantity": 1, "cost_type": "UNAVAILABLE",
            "source": None, "checked_at": None, "confidence": "low", "status": "UNAVAILABLE"}
            for category in profile.get("budget_categories", ["hotel", "transit", "food", "attractions", "misc", "emergency"] if rail and profile.get('domestic_trip') is True else ["flight", "hotel", "transit", "food", "attractions", "internet", "insurance", "visa_related", "misc", "emergency"])]
    from handbook_validation import prepare_required_costs,validate_boundaries,verification_priority
    out['required_cost_coverage']=prepare_required_costs(out)
    out['lodging_continuity']=validate_boundaries(out)
    out['verification_priority']=verification_priority(out,now)
    budget = reconcile_budget(profile, out["cost_ledger"], all_quotes, out.get("exchange_rates"), now=now)
    out["budget_reconciliation"] = budget
    out["budget_status"] = {"user_budget_limit": budget["user_budget_limit_per_person"], "currency": budget["currency"],
        "scope": "PER_PERSON", "current_verified_cost": budget["verified_cost_per_person"],
        "current_estimated_cost": budget["estimated_cost_per_person"], "current_plan_cost": budget["per_person_total"],
        "lowest_found_cost": None, "realistic_minimum_cost": None, "minimum_known_cost": budget["minimum_known_cost_per_person"],
        "budget_gap": budget["budget_gap_per_person"], "feasibility": budget["feasibility"],
        "evidence_status": "PARTIAL" if budget["unknown_cost_categories"] else "VERIFIED_OR_ESTIMATED"}
    # Preserve established conflict detection, dropping the obsolete route fragment gate.
    legacy = legacy_plan_qa(out)
    conflicts = [x for x in legacy["findings"] if x["code"] not in {"ROUTE_COMPLETENESS_CONFLICT", "BUDGET_CONFLICT"}]
    if budget["replanning_required"]:
        conflicts.append({"code": "BUDGET_CONFLICT", "priority": "HARD_CONSTRAINT", "reason": "Reconciled minimum known cost exceeds user limit", "gap": budget["budget_gap_per_person"]})
    consistency = validate_state(out, check_readiness=False)
    if input_consistency['issues']:
        existing={(r['code'],r['field']) for r in consistency['issues']}
        consistency['issues'].extend({**r,'origin':'input_state'} for r in input_consistency['issues'] if (r['code'],r['field']) not in existing)
        consistency['status']='FAIL'
    blockers = []
    if out['required_cost_coverage']['unknown_required_edges']:blockers.append('REQUIRED_TRANSPORT_COST_UNVERIFIED')
    for error in out['lodging_continuity']['errors']+out['required_cost_coverage']['errors']:
        blockers.append(error['code']);conflicts.append({**error,'priority':'HARD_CONSTRAINT'})
    if out['lodging_continuity']['warnings']:blockers.append('SEASONAL_LODGING_UNVERIFIED')
    if len({r['place_id'] for r in out['lodging_continuity']['overnights']})>1:blockers.append('OVERNIGHT_PROPERTY_QUOTES_UNVERIFIED')
    if consistency["status"] == "FAIL": blockers.append("STATE_CONSISTENCY_FAILED")
    if not profile.get("start_date") or not profile.get("end_date"): blockers.append("EXACT_DATES_MISSING")
    for kind, validation in out["quote_validation"].items():
        if validation['status'] == 'NOT_APPLICABLE': continue
        if validation["status"] != "VERIFIED":
            blockers.append(f"EXACT_{kind.upper()}_QUOTE_MISSING")
            if validation.get("refresh_reason") == "EXPIRED": blockers.append(f"{kind.upper()}_QUOTE_REFRESH_REQUIRED")
    if rail:
        # A useful rail handbook is permitted; absence of a ticket contract must
        # never turn an unquoted journey into READY_FOR_BOOKING.
        blockers.append('INTERCITY_TICKET_UNVERIFIED')
        if not all(profile.get(k) for k in ('origin_station','arrival_station','departure_station','return_station')):
            blockers.append('STATION_UNRESOLVED')
    elif not all(profile.get(k) for k in ("origin_airport", "arrival_airport", "departure_airport", "return_airport")):
        blockers.append("AIRPORT_UNRESOLVED")
    if not profile.get("hotel") or not profile.get("hotel_address"): blockers.append("HOTEL_PROPERTY_UNRESOLVED")
    if route_structure != "COMPLETE": blockers.append("ROUTE_STRUCTURE_INCOMPLETE")
    if route_verification != "EXECUTION_VERIFIED": blockers.append("ROUTE_VERIFICATION_INCOMPLETE")
    critical_pending = [x for d in closure_days for x in d["unresolved_edges"] if x["critical"]]
    if critical_pending: blockers.append("CRITICAL_ROUTE_EDGES_UNRESOLVED")
    if budget["feasibility"] == "UNVERIFIED": blockers.append("BUDGET_FEASIBILITY_UNVERIFIED")
    if budget["feasibility"] == "INFEASIBLE": blockers.append("BUDGET_CONFLICT_UNRESOLVED")
    if budget["issues"]: blockers.append("COST_LEDGER_INVALID")
    operational_nodes = [n for d in out.get("days", []) for n in d["execution_graph"]["nodes"] if n["role"] == "ACTIVITY"]
    operations_checked = bool(operational_nodes) and all(n.get("operations_checked") is True and (n.get("source_url") or n.get("source")) and not freshness(n, "attraction_static", now=now)["refresh_required"] for n in operational_nodes)
    if not operations_checked: blockers.append("ATTRACTION_OPERATIONS_UNVERIFIED")
    if profile.get("walking_tolerance_steps") and any(not d.get("estimated_steps") or not d.get("steps_basis") for d in out.get("days", [])):
        blockers.append("WALKING_LIMIT_CHECK_INCOMPLETE")
    if conflicts: blockers.append("ITINERARY_CONFLICT_UNRESOLVED")
    capability = deepcopy(out.get("provider_capability_matrix", {}))
    for kind in ("hotel", "flight"):
        if kind == 'flight' and rail: continue
        key = f"{kind}_exact_quote"
        if out["quote_validation"][kind]["status"] != "VERIFIED" and capability.get(key, "UNKNOWN") not in {"AVAILABLE", "PARTIAL"}:
            blockers.append(f"PROVIDER_{kind.upper()}_QUOTE_{capability.get(key, 'UNKNOWN')}")
    out["provider_capability_matrix"] = capability
    blockers = sorted(set(blockers))
    fail = consistency["status"] == "FAIL" or route_structure == "INCOMPLETE" or bool(conflicts) or bool(budget["issues"])
    confirmation = any(r.get("confirmation_status") == "AWAITING_USER" for r in out.get("selection_status", {}).values() if isinstance(r, dict))
    if fail:
        state = "BLOCKED"
    elif not out.get("days"):
        state = "PROVISIONAL"
    elif any(q.get("refresh_reason") == "EXPIRED" for q in out["quote_validation"].values()):
        state = "DATA_PARTIAL"
    elif blockers:
        state = "EXECUTION_PARTIAL" if route_verification != "EXECUTION_VERIFIED" or budget["closure_status"] != "PASS" else "DATA_PARTIAL"
    else:
        state = "READY_FOR_CONFIRMATION" if confirmation else "READY_FOR_BOOKING"
    qa_layers = {"structural_qa": "PASS" if route_structure == "COMPLETE" else "FAIL",
        "decision_qa": "FAIL" if any(i["code"] == "SELECTION_CONFIRMATION_CONFLICT" for i in consistency["issues"]) else "PASS",
        "constraint_qa": "FAIL" if conflicts else "PARTIAL" if "WALKING_LIMIT_CHECK_INCOMPLETE" in blockers else "PASS",
        "route_qa": "PASS" if route_verification == "EXECUTION_VERIFIED" else "PARTIAL",
        "budget_qa": "FAIL" if budget["feasibility"] == "INFEASIBLE" or budget["issues"] else "UNVERIFIED" if budget["feasibility"] == "UNVERIFIED" else "PASS",
        "data_qa": "PASS" if not blockers else "PARTIAL",
        "execution_qa": "FAIL" if fail else "PASS" if not blockers else "PARTIAL",
        "document_qa": (out.get("document_validation") or {}).get("overall", "UNVERIFIED")}
    readiness = {"plan_status": state, "data_status": "VERIFIED" if not blockers else "PARTIAL",
        "booking_readiness": "READY" if state == "READY_FOR_BOOKING" else "NOT_READY",
        "travel_plan_readiness": state, "execution_readiness": "READY" if not blockers else "NOT_READY" if fail else "PARTIAL",
        "route_structure_status": route_structure, "route_coverage": out["route_closure"]["route_coverage"],
        "route_verification_status": route_verification, "plan_qa": "FAIL" if fail else "PARTIAL" if blockers else "PASS",
        "exact_date_hotel_quote": out["quote_validation"]["hotel"]["status"],
        "exact_date_flight_quote": out["quote_validation"]["flight"]["status"], "blocking_reasons": blockers}
    out["readiness"] = readiness
    out["execution_evaluation"] = {**qa_layers, "blocking_reasons": blockers,
        "state_consistency": consistency["status"], "evaluated_at": now if isinstance(now, str) else datetime.now(timezone.utc).isoformat(timespec="seconds")}
    checks = [{"check": key, "status": value} for key, value in qa_layers.items()]
    out["data_completeness_matrix"] = [
        {"data": "日期与人数", "status": "VERIFIED" if profile.get("start_date") and profile.get("end_date") and profile.get("traveler_count") else "UNAVAILABLE"},
        {"data": "酒店目标日期报价", "status": out["quote_validation"]["hotel"]["status"]},
        {"data": "铁路目标日期票价与时刻" if rail else "往返机票目标日期报价", "status": "UNAVAILABLE" if rail else out["quote_validation"]["flight"]["status"]},
        {"data": "路线结构", "status": route_structure}, {"data": "路线核验", "status": route_verification},
        {"data": "实际成本", "status": budget["feasibility"]},
        {"data": "景点运营", "status": "VERIFIED" if operations_checked else "PARTIAL"},
        {"data": "天气", "status": out.get("weather_data_status", "FORECAST_PENDING")},
        {"data": "数据能力", "status": "PARTIAL" if any(v != "AVAILABLE" for v in capability.values()) else "UNKNOWN" if not capability else "AVAILABLE"}]
    out["plan_qa"] = {"status": readiness["plan_qa"], "findings": conflicts+consistency["issues"],
                      "layers": qa_layers, "checks": checks, "readiness": readiness,
                      "data_completeness_matrix": out["data_completeness_matrix"]}
    final_consistency = validate_state(out)
    if consistency['issues']:
        final_consistency={'status':'FAIL','issues':consistency['issues']+final_consistency['issues']}
    out["state_consistency"] = final_consistency
    def strip(value):
        if isinstance(value, dict):
            value.pop("destination_choice_confirmed", None)
            for child in value.values(): strip(child)
        elif isinstance(value, list):
            for child in value: strip(child)
    strip(out)
    return out
