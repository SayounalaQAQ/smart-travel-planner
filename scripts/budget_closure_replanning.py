"""Cost-ledger adapter for the existing bounded replanner; no network or purchases."""
from copy import deepcopy
from execution_readiness import evaluate_plan
from replanning import replan

MAX_BUDGET_REPLAN_ROUNDS = 3
AREA_RESEARCH = ["Minami", "Honmachi", "Tennoji", "Umeda"]


def budget_research_tasks(profile):
    window = f"{profile.get('start_date')}..{profile.get('end_date')}"
    return {"max_rounds": MAX_BUDGET_REPLAN_ROUNDS, "hotel_provider_retries": 4,
            "flight_provider_retries": 4, "route_provider_retries": 3,
            "resolution_order": ["remove_optional_paid_items", "hotel_candidates", "lodging_areas",
                                 "lodging_savings_minus_transit_delta", "food_strategy", "flight_combinations",
                                 "nearby_dates_only_if_authorized", "best_found_cost", "user_tradeoff"],
            "tasks": [{"area": area, "query": f"{area} Osaka {window} {profile.get('traveler_count')} adults room stay total; airport/Kyoto access cost",
                       "status": "PENDING"} for area in AREA_RESEARCH],
            "date_changes_allowed": profile.get("date_flexibility_authorized") is True}


def replan_budget(initial_plan, candidate_batches, *, now=None, change_threshold=.05,
                  minimum_savings_per_person=150, max_rounds=MAX_BUDGET_REPLAN_ROUNDS):
    if not 1 <= max_rounds <= MAX_BUDGET_REPLAN_ROUNDS:
        raise ValueError("budget replanning must be bounded to 1..3 rounds")
    if len(candidate_batches) > max_rounds:
        raise ValueError("too many supplied research rounds")
    current = evaluate_plan(initial_plan, now=now)
    before = deepcopy(current["budget_reconciliation"])
    history, attempts = [], []
    if not before["replanning_required"]:
        return {"status": "NOT_VERIFIABLE" if before["feasibility"] == "UNVERIFIED" else "NO_CONFLICT",
                "initial_budget": before, "final_budget": before, "final_plan": current,
                "revision_ledger": [], "research_tasks": [], "user_question_count": 0}
    for round_index, candidates in enumerate(candidate_batches, 1):
        options = []
        evaluated = {}
        old_budget = current["budget_reconciliation"]
        for candidate in candidates:
            proposed = evaluate_plan(candidate["plan"], now=now)
            cost = proposed["budget_reconciliation"]
            p = proposed["trip_profile"]
            original = current["trip_profile"]
            violations = []
            if not str(candidate.get('source_url', '')).startswith('https://') or not candidate.get('checked_at'):
                violations.append('candidate revision provenance missing')
            for key in ("start_date", "end_date", "traveler_count", "budget_amount", "budget_currency", "budget_scope"):
                if p.get(key) != original.get(key): violations.append(f"hard fact changed: {key}")
            if original.get("lodging_area_priority") == "HARD_CONSTRAINT" and p.get("lodging_area") != original.get("lodging_area"):
                violations.append("hard lodging area changed")
            if proposed["state_consistency"]["status"] != "PASS": violations.append("state inconsistent")
            if any(x.get('code') != 'BUDGET_CONFLICT' for x in proposed['plan_qa']['findings']):
                violations.append("nonbudget user constraint or itinerary conflict")
            if cost["unknown_cost_categories"] or cost["issues"] or cost["per_person_total"] is None:
                violations.append("candidate full-trip cost not reconciled")
            hotel_check = proposed["quote_validation"]["hotel"]
            flight_check = proposed["quote_validation"]["flight"]
            if hotel_check["status"] != "VERIFIED" or flight_check["status"] != "VERIFIED":
                violations.append("candidate needs valid target-date hotel and flight quotes")
            # The cost ledger, including transit, is mandatory. Candidate metadata
            # cannot substitute an unpriced transfer delta with a claimed saving.
            if not any(row.get("category") == "transit" and row.get("status") == "ACCOUNTED" for row in cost["rows"]):
                violations.append("transit delta not accounted")
            attempts.append({"round": round_index, "candidate": candidate.get("id"), "issues": violations,
                             "budget": {key: cost.get(key) for key in ("party_total", "per_person_total", "unknown_cost_categories", "feasibility")}})
            if violations: continue
            old_cost = old_budget["per_person_total"] or old_budget["minimum_known_cost_per_person"]
            saving = old_cost-cost["per_person_total"]
            extra_time = max(0, candidate.get("additional_total_transit_minutes", 0))
            # Utility penalty is a stated heuristic, never a monetary expense.
            threshold = max(minimum_savings_per_person, old_cost*change_threshold)
            time_penalty = extra_time/60 * candidate.get("time_preference_penalty_per_hour", 10)
            if saving-time_penalty < threshold:
                attempts[-1]["issues"].append("change below materiality threshold after travel-time penalty")
                continue
            cid = candidate["id"]
            evaluated[cid] = proposed
            source = candidate.get("source_url")
            options.append({"id": cid, "name": candidate.get("name", cid),
                "source_url": source, "checked_at": candidate.get("checked_at"),
                "hard_constraints": {"budget": cost["feasibility"] in {"FEASIBLE", "NEAR_LIMIT"}},
                "soft_constraints": candidate.get("soft_constraints", {}),
                "total_trip_cost_per_person": cost["per_person_total"],
                "scores": {"budget": 1, "interests": candidate.get("interest_fit", .8)},
                "why_selected": candidate.get("reason", "Validated full-trip cost improves after including added transit"),
                "impact": {"saving_per_person": round(saving, 2), "additional_total_transit_minutes": extra_time,
                           "time_penalty_heuristic": round(time_penalty, 2)},
                "plan_patch": {"budget_state": {"current_plan_cost": cost["per_person_total"]}}})
        adapted = {"decisions": {"lodging_area": current["trip_profile"].get("lodging_area")},
                   "budget_state": {"current_plan_cost": old_budget["per_person_total"] or old_budget["minimum_known_cost_per_person"]}}
        profile = {**current["trip_profile"], "budget_amount": old_budget["user_budget_limit_per_person"], "budget_scope": "PER_PERSON", "auto_decision_mode": True}
        result = replan(profile, adapted, {"lodging_area": options}, max_rounds=1)
        if result["revision_ledger"]:
            selected_id = result["revision_ledger"][-1]["new_decision"]
            current = evaluated[selected_id]
            history.extend(result["revision_ledger"])
            if not current["budget_reconciliation"]["replanning_required"]: break
        elif evaluated:
            # Retain the lowest fully costed alternative even when no option
            # satisfies the cap. The cap remains hard and readiness stays blocked.
            option = min(options, key=lambda r: r["total_trip_cost_per_person"])
            proposed = evaluated[option["id"]]
            history.append({"old_decision": current["trip_profile"].get("lodging_area"),
                "new_decision": option["id"], "trigger": "BUDGET_CONFLICT",
                "evidence": {"source_url": option["source_url"], "checked_at": option["checked_at"],
                             "hotel_quote_id": proposed["trip_profile"].get("hotel_quote_id"),
                             "flight_quote_id": proposed["trip_profile"].get("flight_quote_id")},
                "reason": "Lowest fully costed alternative found; budget gap remains, hard cap not relaxed",
                "impact": option["impact"], "resolution_status": "BEST_FOUND_INFEASIBLE"})
            current = proposed
    current.setdefault("revision_ledger", []).extend(history)
    current['budget_status']['lowest_found_cost']=current['budget_reconciliation']['per_person_total']
    return {"status": "REPLANNED" if history and not current["budget_reconciliation"]["replanning_required"] else "BEST_FOUND_INFEASIBLE" if history else "BEST_FOUND_PENDING_DATA_OR_CONFLICT",
            "initial_budget": before, "final_budget": current["budget_reconciliation"],
            "final_plan": current, "revision_ledger": history, "candidate_audit": attempts,
            "best_found_cost_per_person": current['budget_reconciliation']['per_person_total'],
            "budget_gap_per_person": current['budget_reconciliation']['budget_gap_per_person'],
            "why_gap_exists": 'No fully costed, constraint-preserving alternative within the cap was found in bounded research' if current['budget_reconciliation']['replanning_required'] else None,
            "research_tasks": budget_research_tasks(current["trip_profile"]),
            "user_question_count": 0, "unresolved_conflict": current["budget_reconciliation"]["replanning_required"],
            "max_rounds": max_rounds, "side_effects": {"booking": False, "payment": False, "personal_data": False}}
