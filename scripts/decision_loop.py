#!/usr/bin/env python3
"""Evidence-gated travel decision compression and research loop helpers.

This module never fetches the web itself. The host agent/MCP supplies real
evidence records; deterministic code validates, ranks, and records them.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from replanning import build_retry_strategy, selection_metadata

DECISION_BUDGET = 3
USER_REQUIRED = {"origin", "travel_window", "duration_days", "traveler_count", "budget_amount", "budget_currency", "budget_scope", "hard_constraints"}


def _valid_candidate(item):
    urls = item.get("source_urls") or ([item.get("source_url")] if item.get("source_url") else [])
    stamp = item.get("checked_at") or item.get("retrieved_at")
    try:
        datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        valid_stamp = True
    except (TypeError, ValueError):
        valid_stamp = False
    return bool(item.get("id") and item.get("name") and valid_stamp and any(str(x).startswith("https://") for x in urls))


def _decision_ready(domain, item):
    """Do not turn a sourced listing into a choice when decisive facts are absent."""
    if domain in {"hotel", "hotels", "lodging"} and item.get("candidate_type", "hotel") == "hotel":
        return all(item.get(key) is not None for key in ("price", "stay_dates", "room_type", "traveler_count"))
    if domain in {"flight", "flights"}:
        return all(item.get(key) is not None for key in ("price", "depart_at", "arrive_at", "airline", "baggage"))
    if domain in {"transit", "routes"}:
        return all(item.get(key) is not None for key in ("duration_minutes", "fare"))
    return True


def ask_value_test(item):
    """Classify a possible question; scores are explicit decision aids, not truth."""
    factors = {key: max(0, min(1, float(item.get(key, 0) or 0))) for key in (
        "user_information_need", "agent_discoverability", "impact_on_plan", "irreversibility", "cost_difference", "preference_dependence")}
    value = (0.25*factors["user_information_need"] + 0.25*(1-factors["agent_discoverability"])
             + 0.2*factors["impact_on_plan"] + 0.1*factors["irreversibility"]
             + 0.1*factors["cost_difference"] + 0.1*factors["preference_dependence"])
    if item.get("field") in USER_REQUIRED:
        priority = "P0"
    elif factors["agent_discoverability"] >= .65:
        priority = "P1"
    elif value >= .55 and factors["preference_dependence"] >= .55:
        priority = "P2"
    else:
        priority = "P3"
    return {**item, "ask_value": round(value, 3), "priority": priority,
            "ask_user": priority == "P0" or (priority == "P2" and value >= .55),
            "agent_action": "ask" if priority == "P0" else ("compare_and_recommend" if priority in {"P1", "P2"} else "default_silently")}


def compress_decisions(items, *, budget=DECISION_BUDGET):
    """Return at most three subjective asks; P0 required facts remain a gate."""
    if not isinstance(budget, int) or budget < 0:
        raise ValueError("decision budget must be a non-negative integer")
    assessed = [ask_value_test(row) for row in items]
    required = [x for x in assessed if x["priority"] == "P0" and x["ask_user"]]
    subjective = sorted((x for x in assessed if x["priority"] == "P2" and x["ask_user"]), key=lambda x: (-x["ask_value"], str(x.get("field", ""))))[:budget]
    return {"decision_budget": budget, "questions": required + subjective,
            "auto_decisions": [x for x in assessed if not x["ask_user"]],
            "overflow": [x for x in assessed if x["priority"] == "P2" and x["ask_user"] and x not in subjective]}


def execute_decision_loop(profile, research_queue, evidence_by_domain, *, auto_decision=False, budget_state=None, potential_questions=None, max_rounds=3):
    """Validate supplied real research, recommend only evidenced candidates, and ledger every choice.

    Agent runtime performs the actual search/fetch/MCP calls between rounds and
    submits their results in ``evidence_by_domain``. Missing data stays unavailable.
    """
    if not isinstance(research_queue, list) or not isinstance(evidence_by_domain, dict):
        raise ValueError("research_queue and evidence_by_domain must be list/object")
    if not 1 <= max_rounds <= 5:
        raise ValueError("max_rounds must be between 1 and 5")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    compressed = compress_decisions(potential_questions or [])
    candidates, decisions, states = {}, [], {}
    claims = {}
    for job in research_queue:
        domain = job.get("domain") if isinstance(job, dict) else None
        if not domain:
            continue
        rows = evidence_by_domain.get(domain, [])
        if isinstance(rows, list):
            for record in rows:
                if isinstance(record, dict) and record.get("claim_key") and record.get("value") is not None:
                    claims.setdefault(str(record["claim_key"]), []).append({"domain": domain, "value": record["value"],
                        "source_url": record.get("source_url"), "source_title": record.get("source_title")})
        sourced = [dict(x) for x in rows if isinstance(x, dict) and _valid_candidate(x)]
        rejected = len(rows) - len(sourced) if isinstance(rows, list) else 0
        candidates[domain] = sourced
        from experience_discovery import experience_match
        accepted = [x for x in sourced if _decision_ready(domain, x) and experience_match(profile,x)['allowed']]
        incomplete = len(sourced) - len(accepted)
        if not accepted:
            states[domain] = "UNAVAILABLE" if (job.get("status") == "unavailable" or not rows) else "EVIDENCE_INCOMPLETE"
            continue
        # Highest explicit recommendation score wins; tie-break is stable by id.
        chosen = max(accepted, key=lambda x: (float(x.get("recommendation_score", 0) or 0)+experience_match(profile,x)['score'], x["id"]))
        state = "AUTO_SELECTED" if auto_decision else "AGENT_RECOMMENDED"
        states[domain] = state
        decisions.append({"decision_id": f"{domain}-{len(decisions)+1}", "category": domain,
            "options_considered": [x["id"] for x in accepted], "selected_option": chosen["id"],
            "why_selected": (chosen.get("why_recommend") or chosen.get("reason") or "按证据完整度、用户约束和候选评分排序。")+'；'+'；'.join(experience_match(profile,chosen)['reasons']),
            "evidence": chosen.get("source_urls") or [chosen["source_url"]],
            "confidence": chosen.get("confidence", "medium"), "user_constraint": profile,
            "tradeoff": chosen.get("tradeoff", ""), "decision_status": state,
            **selection_metadata("AUTO_SELECTED" if auto_decision else "AGENT_SELECTED"),
            "checked_at": chosen.get("checked_at") or chosen.get("retrieved_at"), "rejected_unverifiable_count": rejected,
            "sourced_but_decision_incomplete_count": incomplete})
    rounds = 1
    replan = []
    conflicts = []
    for key, records in claims.items():
        distinct = {json.dumps(item["value"], ensure_ascii=False, sort_keys=True) for item in records}
        if len(distinct) > 1:
            conflicts.append({"claim_key": key, "records": records, "resolution": "preserve_conflict_and_research_authoritative_source"})
            replan.append({"trigger": "evidence_conflict", "claim_key": key,
                "action": "research an authoritative or more recent source before selecting a value"})
    if budget_state and isinstance(budget_state, dict):
        total, limit = budget_state.get("estimated_total"), budget_state.get("limit")
        if isinstance(total, (int, float)) and isinstance(limit, (int, float)) and total > limit:
            rounds = min(max_rounds, 2)
            replan.append({"trigger": "budget_over_limit", "action": "research cheaper evidenced lodging/transport candidates, recalculate, then re-optimize route", "gap": round(total-limit, 2)})
    selections = {}
    for domain, state in states.items():
        selections[domain] = {"status": state,
            "selection_source": ("AUTO_SELECTED" if auto_decision else "AGENT_SELECTED") if state in {"AUTO_SELECTED", "AGENT_RECOMMENDED"} else None,
            "confirmation_status": "NOT_REQUIRED" if state == "AUTO_SELECTED" else "AWAITING_USER" if state == "AGENT_RECOMMENDED" else "NOT_REQUIRED"}
    retry_plans = {}
    for domain, state in states.items():
        retry_domain = {"lodging": "hotels", "hotel": "hotels", "flight": "flights"}.get(domain, domain)
        if state in {"EVIDENCE_INCOMPLETE", "UNAVAILABLE"} and retry_domain in {"hotels", "flights"}:
            retry_plans[domain] = build_retry_strategy(retry_domain, profile)
    return {"state": "DECISION_LOOP_COMPLETE" if not replan else "RESEARCH_REQUIRED",
        "profile": profile, "rounds": rounds, "research_queue": research_queue,
        "candidates": candidates, "decision_ledger": decisions,
        "questions": compressed["questions"],
        "user_decision_ledger": [{"question": x.get("question"), "reason": x.get("reason"), "options": x.get("options", []),
            "impact": x.get("impact"), "default_recommendation": x.get("default_recommendation"), "ask_value": x["ask_value"]}
            for x in compressed["questions"] if x["priority"] == "P2"],
        "domain_status": states, "selection_status": selections, "bounded_retry_plans": retry_plans,
        "replanning_policy": {"max_rounds": 3, "resolve_conflicts_before_user_escalation": True,
            "priority_order": ["HARD_CONSTRAINT", "SOFT_CONSTRAINT", "PREFERENCE", "OPTIONAL"],
            "user_decision_budget": DECISION_BUDGET, "side_effects_enabled": False},
        "evidence_conflicts": conflicts, "replan_triggers": replan, "auto_decision_mode": bool(auto_decision),
        "side_effects": {"booking": False, "payment": False, "personal_data_submission": False}, "updated_at": now}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args(); payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = execute_decision_loop(payload.get("profile", {}), payload.get("research_queue", []), payload.get("evidence_by_domain", {}),
        auto_decision=payload.get("auto_decision", False), budget_state=payload.get("budget_state"),
        potential_questions=payload.get("potential_questions"))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True); Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"state": result["state"], "decisions": len(result["decision_ledger"]), "domain_status": result["domain_status"]}, ensure_ascii=False))


if __name__ == "__main__": main()
