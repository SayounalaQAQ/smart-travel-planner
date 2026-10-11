"""Shared deterministic validation and budget helpers."""
import json
import re
from datetime import datetime, timezone

def budget(data):
    if isinstance(data.get('budget'),dict): data=data['budget']
    cats=('transport','accommodation','attractions','food','shopping','internet','insurance','visa_related','misc','emergency')
    count=int(data.get('traveler_count',1))
    if count<1: raise ValueError('traveler_count must be positive')
    def calc(values):
        out={k:float(values.get(k,0) or 0) for k in cats}
        if any(v<0 for v in out.values()): raise ValueError('Budget components cannot be negative')
        out['total']=round(sum(out.values()),2); out['per_person']=round(out['total']/count,2); return out
    scenarios={k:calc(data[k]) for k in ('low','recommended','comfortable') if isinstance(data.get(k),dict)}
    if not scenarios: scenarios={'estimate':calc(data)}
    return {'currency':data.get('currency','unspecified'),'traveler_count':count,'scenarios':scenarios}

_PLACEHOLDERS={'unknown','unspecified','tbd','待确认','未提供','未知','未确定','待定','不清楚','无'}
_BROAD_DESTINATIONS={'japan','日本','korea','south korea','韩国','欧洲','europe','asia','亚洲','美国','usa','united states','中国','china'}

# Profile facts are classified by who can reliably resolve them, not by whether
# they happen to be missing. A missing agent-discoverable fact is a research task.
PROFILE_FIELD_CLASSES={
    'destination':'USER_REQUIRED','destination_scope':'USER_REQUIRED','origin':'USER_REQUIRED','travel_window':'USER_REQUIRED','start_date':'USER_REQUIRED',
    'end_date':'USER_REQUIRED','duration_days':'USER_REQUIRED','traveler_count':'USER_REQUIRED',
    'traveler_type':'USER_REQUIRED',
    'budget_amount':'USER_REQUIRED','budget_currency':'USER_REQUIRED','budget_scope':'USER_REQUIRED',
    'special_constraints':'USER_REQUIRED','visa_constraints':'USER_REQUIRED',
    'date_flexibility':'USER_REQUIRED','budget_flexibility':'USER_REQUIRED',
    'interests':'USER_REQUIRED','avoid_list':'USER_REQUIRED','pace':'USER_REQUIRED',
    'walking_tolerance_steps':'USER_REQUIRED','food_preferences':'USER_REQUIRED','weather_tolerance':'USER_REQUIRED',
    'must_visit':'USER_REQUIRED','fixed_flight':'USER_REQUIRED','fixed_activity':'USER_REQUIRED',
    'lodging_area':'AGENT_DISCOVERABLE',
    'lodging_candidates':'AGENT_DISCOVERABLE','airport_candidates':'AGENT_DISCOVERABLE',
    'flight_candidates':'AGENT_DISCOVERABLE','attraction_candidates':'AGENT_DISCOVERABLE',
    'transit_candidates':'AGENT_DISCOVERABLE','restaurant_candidates':'AGENT_DISCOVERABLE',
    'route_candidates':'AGENT_DISCOVERABLE','ticket_candidates':'AGENT_DISCOVERABLE',
    'lodging_recommendation':'USER_DECISION','flight_recommendation':'USER_DECISION',
    'attraction_recommendations':'USER_DECISION','transit_recommendation':'USER_DECISION',
    'restaurant_recommendations':'USER_DECISION','destination_choice':'USER_DECISION',
}
DECISION_STATUSES={'DISCOVERING','PROPOSED','USER_DECISION_REQUIRED','AUTO_SELECTED','CONFIRMED'}


def classify_profile_fields(profile):
    """Classify known profile fields; unavailable research stays explicit."""
    classified={}
    for field,kind in PROFILE_FIELD_CLASSES.items():
        value=profile.get(field)
        if isinstance(value,dict) and value.get('status')=='unavailable':
            classified[field]={'class':'UNAVAILABLE','status':'unavailable','reason':value.get('reason')}
        elif value is not None and value != [] and value != {}:
            classified[field]={'class':kind,'status':'known' if kind=='USER_REQUIRED' else 'proposed_or_known'}
        else:
            classified[field]={'class':kind,'status':'research_required' if kind=='AGENT_DISCOVERABLE' else 'not_provided'}
    return classified


def ask_value_test(item):
    """Only permit questions requiring user facts, preferences, or approval."""
    return item.get('class') in {'USER_REQUIRED','USER_DECISION'} and item.get('decision_status') != 'DISCOVERING'


def decision_mode(text):
    """Detect explicit delegation without inferring consent from silence."""
    import re
    return bool(re.search(r'你(?:来|帮我)?(?:决定|安排|挑|选)|全帮我决定|都帮我决定|你觉得合适就行|按你觉得合适的来|你看着办|交给你|随便(?:你安排)?|我都不知道|都可以|全部交给你|I(?:\s+)?(?:trust you|leave it to you|choose for me)',str(text),re.I))


def discovery_workflow(profile, *, auto_decision=False, required_missing=None):
    """Return research work and two-level planning state without inventing candidates."""
    domains=('lodging','flights','airports','attractions','transit','restaurants','routes','tickets')
    return {
        'state':'RESEARCHING','planning_level':'LEVEL_1_PROVISIONAL',
        'decision_mode':'AUTO_DECISION_MODE' if auto_decision else 'USER_CHOICE_MODE',
        'research_queue':[{'domain':name,'status':'DISCOVERING','query_context':profile.get('destination')} for name in domains],
        'candidate_sets':{'lodging_candidates':[],'airport_candidates':[],'flight_candidates':[],
                          'attraction_candidates':[],'transit_candidates':[],'restaurant_candidates':[],
                          'route_candidates':[],'ticket_candidates':[]},
        'recommendations':{'lodging_recommendation':None,'flight_recommendation':None,
                           'attraction_recommendations':[],'transit_recommendation':None,
                           'restaurant_recommendations':[]},
        'selection_status':{name:'DISCOVERING' for name in domains},
        'anchor_type':'AREA_LEVEL_ANCHOR' if profile.get('lodging_area') or profile.get('lodging_candidates') else 'DESTINATION_AREA_ANCHOR',
        'next_state':'USER_REQUIRED_INFO_PENDING' if any(x!='destination_choice' for x in (required_missing or [])) else 'PROVISIONAL_PLAN',
        'after_research_state':'USER_REQUIRED_INFO_PENDING' if any(x!='destination_choice' for x in (required_missing or [])) else ('FINAL_OPTIMIZATION' if auto_decision else 'USER_DECISION_REQUIRED'),
        'limitation':'候选集必须由带来源的实际研究填充；搜索不可用时标记 UNAVAILABLE，不得伪造。'
    }


def _present(value):
    if value is None or value is False: return False
    if isinstance(value,str): return bool(value.strip()) and value.strip().casefold() not in _PLACEHOLDERS
    return True


def _profile(data):
    return data.get('trip_profile') if isinstance(data.get('trip_profile'),dict) else (data.get('critical_info') if isinstance(data.get('critical_info'),dict) else data)


def _field(data, profile, key, *aliases):
    for mapping in (profile,data):
        for name in (key,*aliases):
            value=mapping.get(name)
            if value is not None: return value
    return None


def _is_assumption(data,key):
    provenance=data.get('field_provenance',{})
    state=provenance.get(key) if isinstance(provenance,dict) else None
    return str(state or '').casefold() in {'assumption','default','inferred','unconfirmed','假设','默认','推测','未确认'}


def _scope_is_complete(scope):
    if not _present(scope): return False
    text=str(scope).casefold()
    unit=any(token in text for token in ('per person','per_person','per traveler','per traveller','人均','每人')) or any(token in text for token in ('total','whole trip','whole party','per party','total party','总预算','总额','两人合计','全程'))
    airfare=any(token in text for token in ('flight included','airfare included','including airfare','含机票','包含机票','含国际交通','含往返机票','flight excluded','excluding airfare','airfare excluded','not including flights','不含机票','不含国际机票','不包括机票','不含国际交通','机票另计'))
    return unit and airfare


def _destination_is_broad(destination, profile):
    # V0.8 schema: a recorded selection is distinct from user confirmation.
    # Keep the old boolean as a read-only compatibility fallback for V0.7 plans.
    source=profile.get('selection_source')
    confirmation=profile.get('confirmation_status')
    if source in {'USER_SELECTED','AGENT_SELECTED','AUTO_SELECTED'} and confirmation in {'NOT_REQUIRED','AWAITING_USER','USER_CONFIRMED'}:
        return False
    if profile.get('destination_resolved') is True or profile.get('destination_choice_confirmed') is True: return False
    scope=str(profile.get('destination_scope') or profile.get('destination_type') or '').casefold()
    if scope in {'country','nation','region','continent','国家','地区','洲'}: return True
    return str(destination or '').strip().casefold() in _BROAD_DESTINATIONS


def trip_readiness(data):
    """Heuristic readiness gate. Missing critical values always force RESEARCH_MODE."""
    profile=_profile(data)
    raw_budget=data.get('budget') if isinstance(data.get('budget'),dict) else {}
    aliases={
        'destination':_field(data,profile,'destination','destination_name'),
        'duration_days':_field(data,profile,'duration_days','duration'),
        'traveler_count':_field(data,profile,'traveler_count','party_size'),
        'travel_window':_field(data,profile,'travel_window','travel_dates','month','start_date'),
        'origin':_field(data,profile,'origin','departure_city','departure_location'),
        'budget_amount':_field(data,profile,'budget_amount','target_budget','budget_total') or raw_budget.get('total') or raw_budget.get('budget_total'),
        'budget_currency':_field(data,profile,'budget_currency','currency') or raw_budget.get('currency'),
        'budget_scope':_field(data,profile,'budget_scope','budget_basis') or raw_budget.get('scope'),
    }
    missing=[]
    for key,value in aliases.items():
        invalid=(not _present(value) or _is_assumption(data,key))
        if key in {'duration_days','traveler_count','budget_amount'}:
            invalid=invalid or not isinstance(value,(int,float)) or isinstance(value,bool) or value<=0
        if key=='budget_scope':
            canonical = value in {'PER_PERSON','PER_PARTY'}
            explicit_airfare = isinstance(profile.get('airfare_included'), bool)
            invalid=invalid or not (_scope_is_complete(value) or (canonical and explicit_airfare))
        if key=='travel_window' and _present(value):
            text=str(value).casefold()
            if any(token in text for token in ('春节','chinese new year','lunar new year')) and not re.search(r'\d{1,2}\s*月|\d{4}[-/.年]\s*\d{1,2}|\d{1,2}[-/.]\d{1,2}',text): invalid=True
        if invalid: missing.append(key)
    if _present(aliases['destination']) and _destination_is_broad(aliases['destination'],profile): missing.append('destination_choice')
    free=profile.get('free_accommodation') is True or (isinstance(profile.get('free_nights'),(int,float)) and profile.get('free_nights')>0)
    if free:
        if not _present(_field(data,profile,'accommodation_location','free_stay_location')): missing.append('accommodation_location')
        if not _present(_field(data,profile,'free_stay_dates','free_nights_dates')): missing.append('free_stay_dates')
    if profile.get('fixed_flight') is True and not _present(profile.get('flight_details')): missing.append('flight_details')
    if profile.get('fixed_activity') is True and not _present(profile.get('fixed_activity_date')): missing.append('fixed_activity_date')
    for field in profile.get('required_confirmation_fields',[]) if isinstance(profile.get('required_confirmation_fields'),list) else []:
        if not _present(_field(data,profile,field)): missing.append(field)
    # Remove duplicates without changing question order.
    missing=list(dict.fromkeys(missing))
    readiness=100 if not missing else max(0,min(79,100-13*len(missing)))
    ready_for_provisional=not any(key!='destination_choice' for key in missing)
    mode='PLANNING_MODE' if not missing else ('PROVISIONAL_MODE' if ready_for_provisional else 'RESEARCH_MODE')
    lodging_location=_field(data,profile,'lodging_location','hotel_address','lodging_address','friend_address')
    location_text=str(lodging_location or '').casefold()
    area_only=any(token in location_text for token in (' area',' neighborhood',' district','区域','片区','商圈','hotel not booked','not booked','酒店未订','酒店未预订'))
    property_anchor=_present(lodging_location) and not area_only
    area_anchor=_present(_field(data,profile,'lodging_area','area_level_anchor','lodging_recommendation')) or (area_only and _present(lodging_location))
    route_state='PROPERTY_LEVEL_ANCHOR' if property_anchor else ('AREA_LEVEL_ANCHOR' if area_anchor or not missing else 'DESTINATION_AREA_ANCHOR')
    status='planning_ready' if not missing else ('provisional_ready' if ready_for_provisional else 'research_only')
    return {'mode':mode,'status':status,'readiness':readiness,
            'score_note':'Heuristic completeness indicator only; not a scientific or travel-quality score.',
            'missing_critical_fields':missing,'ready_for_formal_plan':not missing,
            'ready_for_provisional_plan':ready_for_provisional,'route_state':route_state}


def detect_hidden_constraints(data):
    """Return concise high/medium impact follow-ups grounded in missing profile fields."""
    profile=_profile(data); state=trip_readiness(data); missing=set(state['missing_critical_fields']); findings=[]
    specs={
      'destination_choice':('HIGH','先研究目的地内适合的城市/区域，并比较预算、兴趣与交通；之后再给你候选和默认推荐。'),
      'destination':('HIGH','你考虑的目的地或类型是什么？如果还没决定，我可以结合出发地、时间和预算推荐候选。'),
      'travel_window':('HIGH','大概哪个月份/年份？如果涉及热门票务或固定活动，请给具体日期。'),
      'origin':('HIGH','你从哪个城市出发？'),
      'traveler_count':('HIGH','一共几位同行？'),
      'duration_days':('HIGH','你计划玩几天？'),
    }
    budget_gaps=missing.intersection({'budget_amount','budget_currency','budget_scope'})
    if budget_gaps:
        findings.append({'field':'budget_scope','impact':'HIGH','reason':'预算口径会改变城市组合、住宿与是否可负担往返交通。','question':'预算金额和币种是什么？是每人还是全团总额，包含往返机票吗？'})
    for key,(impact,question) in specs.items():
        if key in missing:
            cls='USER_DECISION' if key=='destination_choice' else 'USER_REQUIRED'
            status='DISCOVERING' if key=='destination_choice' else None
            item={'field':key,'impact':impact,'class':cls,'reason':'该信息会改变目的地选择、预算、入境或路线可行性。','question':question}
            if status: item['decision_status']=status
            findings.append(item)
    for key,question in (('accommodation_location','朋友/亲属住在哪座城市或哪个区域？'),('free_stay_dates','可以免费住的具体是哪几晚，或由谁决定日期？'),('flight_details','请提供固定航班的抵达/返程日期、机场和大致时刻。'),('fixed_activity_date','固定活动是哪一天、什么时间？')):
        if key in missing: findings.append({'field':key,'impact':'HIGH','class':'USER_REQUIRED','reason':'会改变免费住宿、固定活动或到达/返程路线。','question':question})
    # Optional preferences are useful but never silently elevated to hard requirements.
    optional=(('pace','旅行节奏偏轻松、平衡还是紧凑？'),('interests','最想优先体验什么？例如美食、动漫、自然、历史或购物？'))
    for key,question in optional:
        if not _present(profile.get(key)): findings.append({'field':key,'impact':'MEDIUM','class':'USER_REQUIRED','reason':'会影响景点取舍和每日安排密度；可跳过并由Agent标记默认假设。','question':question})
    return findings


def personalize_candidate_clusters(profile,candidates):
    """Rank already-researched clusters against explicit preferences; scores are advisory only."""
    interests={str(value).casefold() for value in profile.get('interests',[])}
    avoid={str(value).casefold() for value in profile.get('avoid_list',[])}
    sleep=str(profile.get('sleep_schedule','')).casefold()
    step_cap=profile.get('walking_tolerance_steps')
    ranked=[]
    for candidate in candidates:
        tags={str(value).casefold() for value in candidate.get('interest_tags',[])}
        if tags & avoid: continue
        from experience_discovery import experience_match
        match=experience_match(profile,candidate)
        if not match['allowed']:continue
        score=3*len(tags&interests)
        score+=match['score']
        reasons=list(match['reasons'])
        if tags&interests: reasons.append('matches stated interests')
        start=str(candidate.get('start_time',''))
        if sleep=='late_start' and start and re.match(r'^(?:0?[5-9]|10)(?::|$)',start):
            score-=5; reasons.append('penalized because user prefers a later start')
        steps=candidate.get('estimated_steps')
        if isinstance(step_cap,(int,float)) and isinstance(steps,(int,float)) and steps>step_cap:
            score-=min(8,2+int((steps-step_cap)/5000)); reasons.append('reduced because estimated walking exceeds user target')
        if profile.get('pace')=='relaxed' and candidate.get('activity_count',0)>3:
            score-=3; reasons.append('reduced for a relaxed pace')
        ranked.append({'candidate':candidate,'score':score,'decision_reasons':reasons})
    return sorted(ranked,key=lambda item:(-item['score'],item['candidate'].get('name','')))


def critical_information_gate(data):
    """Backward-compatible view of the V0.4 planning mode gate."""
    state=trip_readiness(data)
    return {'status':state['status'],'ready_for_final':state['ready_for_formal_plan'],
            'ready_for_provisional':state['ready_for_provisional_plan'],'missing':state['missing_critical_fields'],'mode':state['mode'],'readiness':state['readiness'],
            'route_state':state['route_state']}

def optimize_budget(data):
    """Greedily reduce the selected costed scenario without changing protected items."""
    scenario_name=data.get('scenario','recommended')
    limit=data.get('target_budget',data.get('budget_limit'))
    if not isinstance(limit,(int,float)) or isinstance(limit,bool) or limit<0:
        raise ValueError('target_budget must be a non-negative number')
    calculated=budget(data)
    base=calculated['scenarios'].get(scenario_name)
    if base is None: raise ValueError(f'Unknown budget scenario: {scenario_name}')
    cats=('transport','accommodation','attractions','food','shopping','internet','insurance','visa_related','misc','emergency')
    adjusted={k:float(base.get(k,0)) for k in cats}
    original=float(base['total']); gap=max(0,round(original-float(limit),2)); selected=[]
    options=[]
    for index,item in enumerate(data.get('saving_options',[])):
        if not isinstance(item,dict): raise ValueError(f'saving_options[{index}] must be an object')
        category=item.get('category'); amount=item.get('max_saving')
        if category not in cats: raise ValueError(f'saving_options[{index}] has invalid category')
        if item.get('protected') is True: continue
        if not isinstance(amount,(int,float)) or isinstance(amount,bool) or amount<0: raise ValueError(f'saving_options[{index}].max_saving must be non-negative')
        if not isinstance(item.get('tradeoff_score'),(int,float)) or not 0<=item['tradeoff_score']<=10: raise ValueError(f'saving_options[{index}].tradeoff_score must be 0..10')
        basis=item.get('basis')
        if basis not in ('verified','estimated'): raise ValueError(f'saving_options[{index}].basis must be verified or estimated')
        if basis=='verified' and not item.get('source_url'): raise ValueError(f'saving_options[{index}] verified savings requires source_url')
        if basis=='estimated' and not item.get('assumption'): raise ValueError(f'saving_options[{index}] estimated savings requires an explicit assumption')
        options.append(item)
    options.sort(key=lambda item:(float(item['tradeoff_score']), -float(item['max_saving']), item['category']))
    used_groups=set()
    for item in options:
        if gap<=0: break
        group=item.get('option_group')
        if group and group in used_groups: continue
        available=adjusted[item['category']]
        saving=min(float(item['max_saving']),available,gap)
        if saving<=0: continue
        adjusted[item['category']]=round(available-saving,2); gap=round(gap-saving,2)
        selected.append({'category':item['category'],'description':item.get('description',''), 'applied_saving':round(saving,2),'basis':item['basis'],'tradeoff_score':float(item['tradeoff_score']),'source_url':item.get('source_url'),'assumption':item.get('assumption')})
        if group: used_groups.add(group)
    total=round(sum(adjusted.values()),2)
    impact_score=sum(float(item['tradeoff_score']) for item in selected)
    impact='low' if impact_score<=3 else ('medium' if impact_score<=8 else 'high')
    return {'currency':calculated['currency'],'scenario':scenario_name,'traveler_count':calculated['traveler_count'],
            'target_budget':float(limit),'budget_limit':float(limit),'current_plan_cost':original,'original_total':original,
            'projected_total':total,'gap':round(max(0,total-float(limit)),2),
            'remaining_gap':round(max(0,total-float(limit)),2),'within_budget':total<=float(limit),
            'adjusted_categories':adjusted,'selected_options':selected,'sacrifice_impact_score':impact_score,
            'sacrifice_impact':impact,
            'protected_categories':['insurance','visa_related','emergency'],
            'unselected_reason':'No remaining gap.' if total<=float(limit) else 'Available unprotected, evidence-labeled savings are insufficient; keep the remaining gap visible.'}

def validate_trip(data):
    issues=[]
    if not data.get('destination'): issues.append('destination is required')
    days=data.get('days',[])
    if not isinstance(days,list): issues.append('days must be an array'); days=[]
    for i,d in enumerate(days,1):
        travel_only = d.get('day_type') in {'ARRIVAL','DEPARTURE'} and bool((d.get('execution_graph') or {}).get('edges'))
        if not d.get('activities') and not travel_only: issues.append(f'day {i} has no activities')
        if isinstance(d.get('estimated_cost'),(int,float)) and d['estimated_cost']<0: issues.append(f'day {i} has negative estimated_cost')
    for i,e in enumerate(data.get('evidence',[]),1):
        if e.get('source_url') and not e['source_url'].startswith(('https://','http://')): issues.append(f'evidence {i} has invalid source_url')
        if e.get('checked_at'):
            try: datetime.fromisoformat(e['checked_at'].replace('Z','+00:00'))
            except Exception: issues.append(f'evidence {i} has invalid checked_at')
    state=trip_readiness(data)
    if state['ready_for_formal_plan']:
        profile=_profile(data)
        lodging=_field(data,profile,'lodging_location','accommodation_location','hotel_address','lodging_address','friend_address')
        for index,day in enumerate(days,1):
            if day.get('execution_graph'):
                from execution_graph import route_closure
                issues.extend(f'day {index} execution graph: {issue}' for issue in route_closure(day['execution_graph'])['issues'])
                continue
            chain=day.get('route_chain')
            if not isinstance(chain,list) or not chain:
                if day.get('route_state') not in {'ROUTE_PENDING','AREA_LEVEL_ANCHOR','DESTINATION_AREA_ANCHOR'}: issues.append(f'day {index} requires a route_chain or explicit route anchor state')
                continue
            area=_field(data,profile,'lodging_area','area_level_anchor')
            if not _present(lodging) and day.get('route_state') not in {'ROUTE_PENDING','AREA_LEVEL_ANCHOR','DESTINATION_AREA_ANCHOR'}:
                issues.append(f'day {index} requires a property or area-level route anchor')
            if not _present(lodging) and not _present(area) and not _present(day.get('route_origin')) and day.get('route_state') in {'AREA_LEVEL_ANCHOR','DESTINATION_AREA_ANCHOR'}:
                issues.append(f'day {index} requires an explicit area-level route origin')
            if ( _present(lodging) or _present(area) ) and day.get('route_state') not in {'ROUTE_PENDING'} and chain:
                declared_origin=day.get('route_origin') or (lodging if _present(lodging) else area)
                first_from=chain[0].get('from') if isinstance(chain[0],dict) else None
                if _present(first_from) and str(first_from).strip().casefold()!=str(declared_origin).strip().casefold():
                    issues.append(f'day {index} first route leg must start at the declared property/area anchor')
            for leg_number,leg in enumerate(chain,1):
                if not isinstance(leg,dict) or not _present(leg.get('from')) or not _present(leg.get('to')):
                    issues.append(f'day {index} route leg {leg_number} requires from and to'); continue
                if isinstance(leg.get('duration_minutes'),(int,float)) and (not leg.get('source_url') or not leg.get('checked_at')):
                    issues.append(f'day {index} route leg {leg_number} has minutes without a source and checked_at')
                if day.get('route_state')=='ROUTE_PENDING' and isinstance(leg.get('duration_minutes'),(int,float)):
                    issues.append(f'day {index} ROUTE_PENDING cannot contain precise leg minutes')
                if leg_number>1 and isinstance(chain[leg_number-2],dict):
                    previous_to=str(chain[leg_number-2].get('to','')).strip().casefold()
                    current_from=str(leg.get('from','')).strip().casefold()
                    if previous_to and current_from and previous_to!=current_from:
                        issues.append(f'day {index} route chain is discontinuous between legs {leg_number-1} and {leg_number}')
    return issues
