"""Canonical user facts live in trip_profile; projections are derived, quotes are not."""
from copy import deepcopy
from datetime import date, timedelta
import re

FACTS = ("start_date", "end_date", "travel_window", "duration_days", "traveler_count", "origin", "destination",
         "origin_airport", "arrival_airport", "departure_airport", "return_airport", "lodging_area",
         "hotel", "hotel_address", "lodging_location", "budget_amount", "budget_currency", "budget_scope",
         "airfare_included", "selection_source", "confirmation_status", "intercity_mode",
         "origin_station", "arrival_station", "departure_station", "return_station")


def sync_profile(plan):
    out = deepcopy(plan)
    profile = out.get("trip_profile") or out.get("profile") or {}
    out["trip_profile"] = deepcopy(profile)
    profile = out["trip_profile"]
    changes = []
    def assign(target, key, value, path):
        if target.get(key) != value:
            changes.append({"field": path, "old": target.get(key), "new": value})
        target[key] = deepcopy(value)
    if profile.get("start_date") and profile.get("end_date"):
        window = f"{profile['start_date']} 至 {profile['end_date']}"
        assign(profile, "travel_window", window, "trip_profile.travel_window")
        provenance = profile.setdefault("field_provenance", {})
        provenance["travel_window"] = "derived from canonical user start_date/end_date"
    original_scope = str(profile.get('budget_scope', '')).casefold()
    if 'airfare_included' not in profile:
        if any(t in original_scope for t in ('flight included','airfare included','including airfare','含往返机票','含机票')):
            profile['airfare_included'] = True
        elif any(t in original_scope for t in ('flight excluded','airfare excluded','机票另计','不含机票')):
            profile['airfare_included'] = False
    if str(profile.get("budget_scope", "")).lower().startswith("per person"):
        profile["budget_scope"] = "PER_PERSON"
    elif str(profile.get("budget_scope", "")).lower().startswith("party"):
        profile["budget_scope"] = "PER_PARTY"
    for key in FACTS:
        if key in profile:
            assign(out, key, profile[key], key)
            if isinstance(out.get("critical_info"), dict):
                assign(out["critical_info"], key, profile[key], f"critical_info.{key}")
    out["profile"] = deepcopy(profile)
    if isinstance(out.get("budget"), dict):
        out["budget"].update(currency=profile.get("budget_currency"), traveler_count=profile.get("traveler_count"),
                             allocation_scope="PER_PARTY")
    for row in out.get("hotels", []):
        row["dates"] = profile.get("travel_window", "日期待明确")
        if row.get("price_status") == "unavailable": row["category"] = "待核验的酒店候选"
    label = "每人" if profile.get("budget_scope") == "PER_PERSON" else "全团"
    summary = (f"{profile.get('travel_window', '日期待明确')}，{profile.get('duration_days', '?')}天，"
               f"{profile.get('traveler_count', '?')}人；从{profile.get('origin', '出发地待明确')}出发。"
               f"目的地：{profile.get('destination', '待选择')}；住宿区域：{profile.get('lodging_area', '待研究')}。"
               f"用户预算上限：{profile.get('budget_currency', '')} {profile.get('budget_amount', '?')} / {label}，实际成本见预算核算。")
    assign(out, "summary", summary, "summary")
    # Retire historical prompts in user-facing lists once canonical facts are known.
    if profile.get('start_date') and profile.get('end_date'):
        for field in ('risks','bookings','checklist'):
            updated=[]
            for text in out.get(field,[]):
                if not isinstance(text,str):updated.append(text);continue
                old=text
                if re.search(r'具体\d*天日期未提供',text):
                    text=f"旅行日期已明确为{profile['travel_window']}；目标日期航班报价、酒店库存和事件日仍须核验。"
                text=re.sub(r'获得确切\d*天日期后：',f"按已确认日期 {profile['travel_window']}：",text)
                if re.search(r'确定实际\d*天日期，确认预算',text):
                    text=f"日期与预算口径已明确：{profile['travel_window']}，{profile.get('budget_currency','')} {profile.get('budget_amount','?')} / {label}；实际总价仍须核算。"
                if profile.get('hotel_address') and '保持区域级锚点' in text:
                    text=text.replace('保持区域级锚点','已取得候选酒店地址，完整门到门路线仍须核验')
                if text!=old:changes.append({'field':field,'old':old,'new':text})
                updated.append(text)
            if field in out:out[field]=updated
    wanaka=next((r for r in out.get('restaurant_candidates',[]) if r.get('place_id')=='wanaka' and r.get('backup')),None)
    if wanaka and isinstance(out.get('food_recommendations'),list):
        out['food_recommendations']=[f"わなか千日前店以章鱼烧小吃为主；若需完整一餐可用{wanaka['backup']}备选。具体坐席、排队和目标日期营业再核。" if isinstance(x,str) and x.startswith('Wanaka：') else x for x in out['food_recommendations']]
    out.setdefault("state_sync_ledger", []).extend(changes)
    return out


def validate_state(plan, *, check_readiness=True):
    p = plan.get("trip_profile") or {}
    issues = []
    def issue(code, field, detail): issues.append({"code": code, "field": field, "reason": detail})
    for replica_key in ("profile", "critical_info"):
        replica = plan.get(replica_key) or {}
        for field in FACTS:
            if field in replica and field in p and replica[field] != p[field]:
                issue("STATE_FACT_MISMATCH", f"{replica_key}.{field}", "Does not match trip_profile")
    for field in FACTS:
        if field in plan and field in p and plan[field] != p[field]:
            issue("STATE_FACT_MISMATCH", field, "Does not match trip_profile")
    try:
        start, end = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        if end < start or (end-start).days+1 != p.get("duration_days"):
            issue("DATE_DURATION_MISMATCH", "trip_profile", "Dates and duration disagree")
        expected_dates = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
        if plan.get("days") and [d.get("date") for d in plan["days"]] != expected_dates:
            issue("DAY_DATES_MISMATCH", "days", "Itinerary day dates do not match the complete canonical date interval")
        if re.search(r"日期.{0,8}(未提供|未定|未知)|exact dates.*(not provided|unknown)|date.*unavailable", str(p.get("travel_window", "")), re.I):
            issue("STALE_DATE_TEXT", "trip_profile.travel_window", "Exact dates exist but window claims unavailable")
        for key in ("summary", "subtitle", "lodging_recommendation", "flight_recommendation","risks","checklist","bookings"):
            if re.search(r"具体\d*天?日期未提供|获得确切\d*天日期后|确定实际\d*天日期|exact dates.*not provided", str(plan.get(key, "")), re.I):
                issue("STALE_DATE_TEXT", key, "Resolved dates and visible historical text disagree")
    except (KeyError, ValueError, TypeError):
        if p.get("start_date") or p.get("end_date"):
            issue("INVALID_CANONICAL_DATES", "trip_profile", "Both valid dates are required")
    for row in plan.get("hotel_availability", []):
        if row.get("price_type") == "EXACT_DATE_PRICE":
            if row.get("check_in") != p.get("start_date") or row.get("check_out") != p.get("end_date"):
                issue("HOTEL_DATES_MISMATCH", "hotel_availability", "Quote does not match trip dates")
            if row.get("guest_count") != p.get("traveler_count"):
                issue("HOTEL_GUEST_COUNT_MISMATCH", "hotel_availability", "Quote party differs")
    for row in plan.get("flight_availability", []):
        if row.get("status") == "EXACT_DATE_QUOTE":
            if row.get("outbound_date") != p.get("start_date") or row.get("return_date") != p.get("end_date"):
                issue("FLIGHT_DATES_MISMATCH", "flight_availability", "Round-trip quote does not match canonical dates")
            if row.get("traveler_count") != p.get("traveler_count"):
                issue("FLIGHT_PARTY_COUNT_MISMATCH", "flight_availability", "Quote party differs")
            if p.get("origin_airport") and row.get("origin_airport") != p["origin_airport"]:
                issue("FLIGHT_AIRPORT_MISMATCH", "flight_availability.origin_airport", "Quote airport differs")
            if p.get("arrival_airport") and row.get("destination_airport") != p["arrival_airport"]:
                issue("FLIGHT_AIRPORT_MISMATCH", "flight_availability.destination_airport", "Quote airport differs")
    def check_selection(value, path):
        if isinstance(value, dict):
            if value.get("selection_source") == "AUTO_SELECTED" and (value.get("confirmation_required") is True or value.get("confirmation_status") == "AWAITING_USER"):
                issue("SELECTION_CONFIRMATION_CONFLICT", path, "AUTO_SELECTED cannot silently require user confirmation")
            for k, child in value.items():
                if k not in {"state_sync_ledger", "revision_ledger", "evidence", "initial_plan"}: check_selection(child, f"{path}.{k}")
        elif isinstance(value, list):
            for i, child in enumerate(value): check_selection(child, f"{path}[{i}]")
    check_selection(plan, "plan")
    budget = plan.get("budget_reconciliation") or {}
    count = p.get("traveler_count")
    if budget:
        if budget.get("traveler_count") != count or budget.get("currency") != p.get("budget_currency"):
            issue("BUDGET_SCOPE_MISMATCH", "budget_reconciliation", "Count or currency differs from profile")
        if budget.get("party_total") is not None and budget.get("per_person_total") is not None and count:
            if abs(budget["party_total"]-budget["per_person_total"]*count) > .02:
                issue("BUDGET_SCOPE_MISMATCH", "budget_reconciliation", "Party/person totals do not reconcile")
    for day in plan.get("days", []):
        graph = day.get("execution_graph") or {}
        nodes = graph.get("nodes", [])
        if nodes:
            if graph.get("date") != day.get("date"):
                issue("GRAPH_DATE_MISMATCH", "execution_graph", "Graph date differs from day date")
            terminal = 'STATION' if p.get('intercity_mode') == 'TRAIN' else 'AIRPORT'
            if day.get("date") == p.get("start_date") and nodes[0].get("role") != terminal:
                issue("ARRIVAL_ORIGIN_INVALID", "execution_graph", "Arrival must start at the selected transport terminal")
            if day.get("date") == p.get("end_date") and (nodes[-1].get("role") != terminal or len([n for n in nodes if n.get("role") == terminal]) < 2):
                issue("DEPARTURE_ROUTE_INVALID", "execution_graph", "Departure requires destination and home transport terminals")
            for n in nodes:
                if n.get("place_id") == "hotel" and p.get("hotel") and n.get("place") != p["hotel"]:
                    issue("HOTEL_GRAPH_MISMATCH", "execution_graph", "Hotel node is stale")
            projected = [n["id"] for n in nodes]
            if day.get("route_sequence") and [s.get("node_id") for s in day["route_sequence"]] != projected:
                issue("GRAPH_PROJECTION_MISMATCH", "route_sequence", "Projection differs from canonical nodes")
            if day.get('activities') is not None:
                expected=[n['id'] for n in nodes if n.get('role') in {'ACTIVITY','MEAL','REST'}]
                if [a.get('node_id') for a in day['activities']] != expected:
                    issue('GRAPH_PROJECTION_MISMATCH','activities','Activities differ from canonical graph nodes')
            if day.get('route_chain') is not None and [e.get('id') for e in day['route_chain']] != [e.get('id') for e in graph.get('edges',[])]:
                issue('GRAPH_PROJECTION_MISMATCH','route_chain','Route chain differs from canonical edges')
    if check_readiness and (plan.get("readiness") or {}).get("booking_readiness") == "READY":
        if (plan.get("execution_evaluation") or {}).get("blocking_reasons"):
            issue("FALSE_BOOKING_READY", "readiness", "Blocking reasons remain")
        if budget.get("feasibility") not in {"FEASIBLE", "NEAR_LIMIT"}:
            issue("FALSE_BOOKING_READY", "readiness", "Budget not reconciled and feasible")
        if p.get('intercity_mode') == 'TRAIN':
            issue('FALSE_BOOKING_READY', 'readiness', 'Rail target-date ticket contract has not been implemented')
        elif not all(p.get(k) for k in ("origin_airport", "arrival_airport", "departure_airport")):
            issue("FALSE_BOOKING_READY", "readiness", "Airport unresolved")
        for kind in ("hotel", "flight"):
            if kind == 'flight' and p.get('intercity_mode') == 'TRAIN': continue
            if (plan.get("quote_validation") or {}).get(kind, {}).get("status") != "VERIFIED":
                issue("FALSE_BOOKING_READY", "readiness", f"Exact {kind} quote not verified")
    return {"status": "FAIL" if issues else "PASS", "issues": issues}
