"""Small cross-module delivery checks; unknown evidence permits provisional planning."""
import re
from datetime import datetime,timezone,timedelta,date
from decimal import Decimal
from cost_ledger import party_amount

def nodes(day):
    return day.get('execution_graph',{}).get('nodes',day.get('execution_nodes',day.get('itinerary_nodes',[])))

def validate_boundaries(plan):
    errors=[];warnings=[];nights=[];previous=None
    def error(code,field,reason,repair):errors.append(dict(code=code,field=field,reason=reason,repair=repair))
    for i,d in enumerate(plan.get('days',[])):
        ns=nodes(d);start=d.get('start_anchor');end=d.get('overnight_anchor')
        if not isinstance(start,dict):start=None
        if not isinstance(end,dict):end=None
        legacy=not d.get('execution_nodes') and not d.get('execution_graph')
        for n in ns:
            if n.get('role')=='ACTIVITY' and re.search(r'高铁车厢|返程高铁|飞行中|夜间列车|^train carriage$|^return train$',str(n.get('place','')),re.I):
                error('TRANSPORT_ACTIVITY_DUPLICATION',f'days[{i}]','Transport vehicle is an activity in addition to terminal routing','用唯一的有序枢纽与交通边表示该行程，不将车厢再作为景点')
                if not plan.get('cost_ledger'):error('REQUIRED_COST_BREAKDOWN_MISSING',f'days[{i}]','Cross-city transport has no linked segment costs','分解城际票、跨站换乘、接驳与地面交通；未知金额留 UNKNOWN，而不是笼统额度')
            if legacy and n.get('role')=='REST' and re.search(r'夜宿|住宿|overnight',str(n.get('activity','')),re.I) and not end:
                error('OVERNIGHT_BOUNDARY_REQUIRED',f'days[{i}]','Overnight lodging differs from implicit base; no explicit boundary','声明 overnight_anchor 与次日 start_anchor；未核实地点保持区域/候选，不自动返回默认酒店')
        if start and ns and start.get('place_id')!=ns[0].get('place_id'):
            error('DAY_START_CONFLICT',f'days[{i}]','Declared start differs from first route node','让有序路线首节点与实际出发位置一致')
        if end and ns and end.get('place_id')!=ns[-1].get('place_id'):
            error('OVERNIGHT_ROUTE_CONFLICT',f'days[{i}]','Declared overnight differs from route endpoint','以真实夜间终点结束，不自动追加默认基地')
        if previous and ns and previous['place_id']!=ns[0].get('place_id'):
            error('OVERNIGHT_CONTINUITY_CONFLICT',f'days[{i}]','Previous overnight is not next-day starting node','次日先从昨晚实际住宿/夜间交通节点出发，再显示转移交通；不要用不同地点开局')
        seen=set()
        for a,b in zip(ns,ns[1:]):
            segment=a.get('transport_segment_id') or b.get('transport_segment_id')
            if segment and segment in seen:
                error('DUPLICATE_TRANSPORT_SEGMENT',f'days[{i}]','Same transport segment appears twice','同一真实交通段只保留一条有序边')
            if segment:seen.add(segment)
        if end:previous=end
        elif ns and ns[-1].get('role') in {'HOTEL','OVERNIGHT','NIGHT_TRANSIT'}:previous=ns[-1]
        else:previous=None
        if previous:nights.append(dict(date=d.get('date'),place_id=previous.get('place_id'),place=previous.get('place'),status=previous.get('status','CANDIDATE')))
        if end and end.get('seasonal') is True:
            required=('operating','heating','hot_water','return_transfer')
            proof=end.get('operational_evidence') or {}
            missing=[k for k in required if not (isinstance(proof.get(k),dict) and proof[k].get('status')=='VERIFIED' and
                proof[k].get('source_url') and proof[k].get('checked_at') and proof[k].get('applicable_date')==d.get('date'))]
            if missing:warnings.append(dict(code='SEASONAL_LODGING_UNVERIFIED',field=f'days[{i}]',reason='Seasonal stay conditions unknown: '+', '.join(missing),repair='不视为可执行；核实营业/供暖/热水与接送，保留市区住宿或取消远端活动的备选'))
    return dict(errors=errors,warnings=warnings,overnights=nights)

def prepare_required_costs(plan):
    """Attach a cost identity to each route change; never fill unknown with zero."""
    ledger=plan.setdefault('cost_ledger',[]);lookup={r.get('id'):r for r in ledger}
    profile=plan.get('trip_profile',{});count=profile.get('traveler_count')
    rail=profile.get('intercity_mode')=='TRAIN'
    included=profile.get('intercity_fare_included') if rail else profile.get('airfare_included')
    for d in plan.get('days',[]):
        places={n.get('id'):n.get('place') for n in d.get('execution_graph',{}).get('nodes',[])}
        for e in d.get('execution_graph',{}).get('edges',[]):
            identifier=e.get('cost_id') or 'route-cost-'+e['id']
            e['cost_id']=identifier
            if identifier in lookup:continue
            intercity=e.get('purpose') in {'flight','cross_city'}
            excluded=intercity and included is False
            free=e.get('mode')=='WALK' and e.get('status') in {'VERIFIED','ESTIMATED','CURRENT_REFERENCE'}
            row=dict(id=identifier,category=e.get('cost_category') or ('intercity_rail' if rail and intercity else 'flight' if e.get('purpose')=='flight' else 'transit'),
                item='必要交通：'+str(places.get(e.get('from_node')) or '出发地点')+' → '+str(places.get(e.get('to_node')) or '目的地点'),amount=0 if free else None,currency=profile.get('budget_currency'),scope='PER_PARTY',quantity=1,traveler_count=count,
                cost_type='ESTIMATED' if free else 'UNAVAILABLE',source_url=e.get('source_url'),checked_at=e.get('checked_at'),
                estimation_basis='步行无交通票费；不包含可能的入场费用' if free else None,
                optional_excluded=excluded,exclusion_reason='用户明确不计入往返城际交通' if excluded else None)
            ledger.append(row);lookup[identifier]=row
    return cost_coverage(plan)

def cost_coverage(plan):
    errors=[];unknown=[];covered=[];profile=plan.get('trip_profile',{});ledger=plan.get('cost_ledger',[])
    lookup={r.get('id'):r for r in ledger};groups={};seen={}
    for d in plan.get('days',[]):
        for e in d.get('execution_graph',{}).get('edges',[]):
            identifier=e.get('cost_id');r=lookup.get(identifier)
            if not r or (r.get('amount') is None and not r.get('optional_excluded')):
                unknown.append(dict(edge_id=e.get('id'),date=d.get('date'),cost_id=identifier,status='UNKNOWN'))
                continue
            prior=seen.get(identifier)
            if prior and not (e.get('id') in r.get('covers_edge_ids',[]) and prior in r.get('covers_edge_ids',[])):
                errors.append(dict(code='SHARED_COST_COVERAGE_INVALID',field=str(identifier),reason='Cost reused across edges without explicit package coverage',repair='为通票/往返套餐列 covers_edge_ids；独立车费使用独立费用 ID'))
            seen[identifier]=e.get('id');covered.append(e.get('id'))
    for r in ledger:
        if r.get('optional_excluded') or r.get('cost_type') in {'USER_BUDGET','UNAVAILABLE'} or r.get('amount') is None:continue
        if r.get('category') not in {'flight','intercity_rail','transit','airport_transfer','station_transfer','charter_transfer','rental_car','transport'}:continue
        try:
            if r.get('currency')!=profile.get('budget_currency'):continue # Existing ledger validates currency conversion.
            groups[r['id']]=party_amount(r,profile['traveler_count'])
        except (ValueError,KeyError,TypeError):continue
    known=sum(groups.values(),Decimal(0))
    raw=plan.get('budget',{});tiers=raw.get('scenarios') or {k:raw[k] for k in ('low','recommended','comfortable') if isinstance(raw.get(k),dict)}
    for name,tier in tiers.items():
        if tier and Decimal(str(tier.get('transport',0)))<known:
            errors.append(dict(code='REQUIRED_TRANSPORT_BUDGET_CONFLICT',field='budget.'+name+'.transport',reason=f'Known necessary transport {known} exceeds allocation',repair='补齐本路线所有交通费用并重新优化；改交通方式则必须另建明细，不能仅保证总额算术正确'))
    return dict(status='CONFLICT' if errors else 'INCOMPLETE' if unknown else 'COVERED',known_transport_amount=float(known),unknown_required_edges=unknown,
        covered_edges=covered,complete_transport_estimate=None if unknown else float(known),errors=errors)

def verification_priority(plan,now=None):
    try:
        today=datetime.fromisoformat(now.replace('Z','+00:00')).date() if now else datetime.now(timezone(timedelta(hours=8))).date()
        remaining=(date.fromisoformat(plan['trip_profile']['start_date'])-today).days
    except (KeyError,ValueError,TypeError):return dict(status='DATE_UNAVAILABLE',actions=[])
    urgent=0<=remaining<=7
    if not urgent:return dict(days_to_departure=remaining,status='NORMAL',actions=[])
    rail=plan['trip_profile'].get('intercity_mode')=='TRAIN'
    items=[('往返铁路与跨站换乘' if rail else '往返航班与机场接驳','先核对目标日期票、时刻、换乘枢纽和完整接驳，缺报价不代表能上车。'),
        ('每晚住宿与退房行李','确认具体门店营业、房型、取消、寄存；季节性住宿另核实供暖、热水及返程接送。'),
        ('关键地面接驳','核实正规交通经营方、接送时刻和完整价格；未确认则缩减远端活动，保留住宿地附近方案。'),
        ('最新天气与预约','查询出行日预报和景点当日预约；安全或运营条件不满足时取消对应活动。')]
    return dict(days_to_departure=remaining,status='DEPARTURE_SOON',actions=[dict(priority=i+1,item=a,note=b,verification_status='CHECK_REQUIRED') for i,(a,b) in enumerate(items)])
