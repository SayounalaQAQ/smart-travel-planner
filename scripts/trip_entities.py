"""Shared sourced places and selected merchants at the existing delivery boundary."""
from copy import deepcopy
from datetime import date
import re


def selected_attractions(plan):
    candidates = plan.get('attractions', [])
    explicit = [x for x in candidates if x.get('selected') is True]
    if explicit: return explicit
    nodes = [n for d in plan.get('days', []) for n in d.get('execution_graph', {}).get('nodes', d.get('execution_nodes', d.get('itinerary_nodes', d.get('activities', [])))) if isinstance(n, dict)]
    matches = [x for x in candidates if x.get('core', True) is not False and x.get('selected') is not False
        and any(n.get('place_id') == x.get('id') or any(a and a in str(n.get('place') or n.get('activity') or '') for a in [x.get('name'), *x.get('aliases', [])]) for n in nodes)]
    return matches or [x for x in candidates if x.get('core', True) is not False and x.get('selected') is not False]


def compare_merchants(candidates, domain, profile):
    """Compare inspected facts, not search ranking or invented review scores."""
    results = []
    for c in candidates:
        proof = c.get('field_evidence', {})
        sources = c.get('source_urls') or [c.get('source_url')]
        eligible = bool(c.get('id') and c.get('name') and c.get('address') and c.get('checked_at')
            and any(str(u).startswith('https://') for u in sources)
            and proof.get('address') and c.get('route_fit') is True and c.get('route_fit_reason'))
        if c.get('hard_conflicts'): eligible = False
        reasons = [c.get('route_fit_reason', '缺少路线匹配依据')]
        score = 0
        # Every awarded preference requires a supplied inspected fact and evidence.
        for key, weight in (('interest_fit', 4), ('solo_fit', 2), ('budget_fit', 3), ('facility_fit', 1)):
            if c.get(key) is True and proof.get(key): score += weight; reasons.append(str(proof[key].get('value', key)))
        detour = c.get('detour_minutes')
        if isinstance(detour, (int, float)) and proof.get('detour_minutes'): score -= min(5, detour / 15)
        unknowns = [k for k in ('target_price', 'recent_independent_reviews', 'cancellation' if domain=='hotel' else 'opening_hours') if not proof.get(k)]
        results.append({'candidate_id': c.get('id'), 'eligible': eligible, 'score': round(score, 2),
            'reasons': reasons, 'unknowns': unknowns, 'source_urls': sources,
            'review_status': 'VERIFIED_SAMPLE' if proof.get('recent_independent_reviews') else 'NO_VERIFIED_RECENT_REVIEW_SAMPLE'})
    eligible = sorted((r for r in results if r['eligible']), key=lambda r: (-r['score'], str(r['candidate_id'])))
    return {'domain': domain, 'selected_id': eligible[0]['candidate_id'] if eligible else None,
        'evaluations': results, 'selection_source': 'AGENT_SELECTED', 'confirmation_status': 'NOT_REQUIRED',
        'status': 'PROVISIONAL_SELECTION' if eligible else 'AREA_ONLY',
        'reason': '优先路线与用户兴趣匹配的有来源商户；报价和评价不足明确保留，不按搜索排名推荐。'}


def prepare_entities(plan):
    out = deepcopy(plan); profile = out.get('trip_profile', {})
    places = out.get('place_registry', [])
    registry = {r['id']: r for r in places if isinstance(r, dict) and r.get('id')}
    hotels = out.get('hotel_candidates', [])
    selected = next((c for c in hotels if c.get('selected') is True), None)
    if hotels and not selected and out.get('auto_decision_mode') is True:
        result = compare_merchants(hotels, 'hotel', profile)
        out['hotel_comparison'] = result
        selected = next((c for c in hotels if c.get('id') == result['selected_id']), None)
    if selected:
        profile.update(hotel=selected['name'], hotel_address=selected['address'], hotel_place_id=selected['id'], lodging_area=selected.get('area', profile.get('lodging_area')))
        selected['selected'] = True
    for day in out.get('days', []):
        key = 'execution_graph' if day.get('execution_graph') else None
        nodes = day[key]['nodes'] if key else day.get('execution_nodes', day.get('itinerary_nodes', []))
        for n in nodes:
            if n.get('role') == 'HOTEL' and selected and n.get('place_id') in {'hotel', selected['id']}:
                n.update(place=selected['name'], address=selected['address'], location_status='RESOLVED')
            place = registry.get(n.get('place_id'))
            if place:
                # Conflicting supplied districts are validated separately, not silently erased.
                n.setdefault('city', place.get('city')); n.setdefault('district', place.get('district'))
                n.setdefault('address', place.get('address')); n['place'] = place.get('name', n.get('place'))
    # Explicit selected merchant costs enter the existing ledger, never duplicate by node/cost ID.
    ledger = out.get('cost_ledger', [])
    for c in [h for h in hotels if h.get('selected') is True] + out.get('restaurant_candidates', []):
        if not c or c.get('selected') is not True: continue
        cost = c.get('planning_cost')
        if not cost: continue
        identifier = 'merchant-' + str(c['id'])
        if any(r.get('id') == identifier for r in ledger): continue
        if not all(k in cost for k in ('amount', 'currency', 'scope', 'quantity', 'cost_type', 'source_url', 'checked_at')): continue
        ledger.append({**cost, 'id': identifier, 'place_id': c['id'], 'item': c['name'],
            'category': 'hotel' if c in hotels else 'food', 'traveler_count': profile.get('traveler_count')})
    if ledger: out['cost_ledger'] = ledger
    return out


def entity_errors(plan):
    errors = []; profile = plan.get('trip_profile', {})
    def error(code, field, reason, repair): errors.append({'code': code, 'field': field, 'reason': reason, 'repair': repair})
    places = plan.get('place_registry', [])
    all_nodes=[n for d in plan.get('days',[]) for n in d.get('execution_graph',{}).get('nodes',d.get('execution_nodes',d.get('itinerary_nodes',[])))]
    for c in plan.get('hotel_candidates',[])+plan.get('restaurant_candidates',[]):
        if c.get('selected') is not True:continue
        if not (c.get('address') and c.get('source_url') and c.get('checked_at') and c.get('field_evidence',{}).get('address')):
            error('MERCHANT_EVIDENCE_INCOMPLETE',str(c.get('id')),'Selected merchant lacks inspected identity/address provenance','读取具体酒店或餐厅门店原页，保存地址来源；不足时退回区域级建议')
        if c in plan.get('restaurant_candidates',[]) and not any(n.get('role')=='MEAL' and n.get('place_id')==c.get('id') for n in all_nodes):
            error('SELECTED_MEAL_NOT_ROUTED',str(c.get('id')),'Selected restaurant is not included in the ordered daily route','把本次选入的餐厅作为 MEAL 节点并核算对应餐费；备选标 selected=false')
    registry = {}
    aliases = {}
    for r in places:
        if r.get('id') in registry and registry[r['id']] != r:
            error('GEOGRAPHIC_ENTITY_CONFLICT', 'place_registry', 'Same place ID has different records', '用已读取的权威地址统一地点记录')
        registry[r.get('id')] = r
        for name in [r.get('name'), *r.get('aliases', [])]:
            if name and name in aliases and aliases[name] != r.get('id'):
                error('GEOGRAPHIC_ENTITY_CONFLICT', 'place_registry', 'One alias maps to different places', '去除歧义别名，标明具体门店或码头')
            aliases[name] = r.get('id')
    for i, day in enumerate(plan.get('days', [])):
        nodes = day.get('execution_graph', {}).get('nodes', day.get('execution_nodes', day.get('itinerary_nodes', [])))
        for n in nodes:
            canonical = registry.get(n.get('place_id'), {})
            for k in ('city', 'district', 'address'):
                if n.get(k) and canonical.get(k) and n[k] != canonical[k]:
                    error('GEOGRAPHIC_ENTITY_CONFLICT', f'days[{i}].{n.get("place_id")}.{k}', 'Node contradicts the sourced place record', '引用同一地点记录，重新核验冲突地址')
        arrival = day.get('day_type') == 'ARRIVAL' or day.get('date') == profile.get('start_date')
        departure = day.get('day_type') == 'DEPARTURE' or day.get('date') == profile.get('end_date')
        origin_ids = {'origin-airport', 'origin-station'}
        arrival_ids = {'arrival-airport', 'arrival-station'}
        hotel_at = next((j for j,n in enumerate(nodes) if n.get('role')=='HOTEL'), None)
        origin_at = next((j for j,n in enumerate(nodes) if n.get('place_id') in origin_ids), None)
        destination_at = next((j for j,n in enumerate(nodes) if n.get('place_id') in arrival_ids), None)
        if arrival and hotel_at is not None and (origin_at is not None and hotel_at < origin_at or destination_at is not None and hotel_at < destination_at):
            error('ARRIVAL_DIRECTION_CONFLICT', f'days[{i}].nodes', 'Destination hotel precedes arrival transport', '出发地枢纽 → 目的地枢纽 → 酒店/景点；不要逆向从当地酒店出发')
        if arrival and not nodes and any('→' in str(a.get('activity','')) and profile.get('origin','?') in str(a.get('activity','')) for a in day.get('activities',[]) if isinstance(a,dict)):
            error('TRAVEL_DAY_NODES_REQUIRED', f'days[{i}].activities', 'Cross-city transport is buried in activity text', '明确枢纽角色和 itinerary_nodes 顺序，不把整条航线当作当地景点')
        if departure:
            constraint = day.get('return_constraint', {})
            if constraint.get('departure_time') and all(isinstance(constraint.get(k),(int,float)) for k in ('airport_buffer_minutes','transfer_allowance_minutes','luggage_minutes')):
                try:
                    def minutes(s):
                        h,m = map(int,s[:5].split(':'))
                        if not 0<=h<=23 or not 0<=m<=59:raise ValueError('Invalid clock')
                        return h*60+m
                    cutoff = minutes(constraint['departure_time']) - sum(constraint[k] for k in ('airport_buffer_minutes','transfer_allowance_minutes','luggage_minutes'))
                    known=[n.get('end_time') or n.get('time') for n in nodes if n.get('role') in {'ACTIVITY','MEAL','HOTEL'}]
                    last = max((minutes(t) for t in known if isinstance(t,str) and re.fullmatch(r'\d{2}:\d{2}',t)), default=0)
                    if last > cutoff: error('RETURN_BUFFER_CONFLICT', f'days[{i}]', 'Sightseeing ends after the luggage/transfer/airport-buffer cutoff', '取消远端景点或移到前一天；用真实班次或明确条件重新计算返回时限')
                except (ValueError,TypeError): error('RETURN_CLOCK_INVALID', f'days[{i}]', 'Return clock cannot be parsed', '使用 HH:MM 与明确的缓冲分钟')
    return errors
