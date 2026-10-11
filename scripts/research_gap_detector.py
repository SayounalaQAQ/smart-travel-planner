"""Scan canonical plan, including new replanned nodes, without fixed destination lists."""
from data_freshness import freshness
from research_ledger import identity
from execution_graph import route_evidence_valid

ATTRACTION_FIELDS={'opening_hours':'ATTRACTION_OPENING','ticket_price':'ATTRACTION_PRICE',
    'reservation_required':'ATTRACTION_RESERVATION','transport_info':'ATTRACTION_ACCESS'}
HOTEL_FIELDS={'address':'HOTEL_LOCATION','nearest_station':'HOTEL_ACCESS',
    'check_in_out':'HOTEL_STATIC','room_categories':'HOTEL_STATIC','breakfast':'HOTEL_STATIC'}
RESTAURANT_FIELDS={'name':'RESTAURANT_STATIC','address':'RESTAURANT_LOCATION',
    'opening_hours':'RESTAURANT_OPENING','cuisine':'RESTAURANT_STATIC',
    'reservation':'RESTAURANT_RESERVATION','price_reference':'RESTAURANT_PRICE_REFERENCE'}

def canonical_gap_id(gap):
    target=gap['target']; kind=target['kind']
    anchor=target.get('edge_id') or target.get('place_id') or target.get('row_id') or target.get('name') or gap['entity']
    date=target.get('date') or gap.get('travel_date') if kind in {'route','walking'} else ''
    return identity(gap['category'],gap['required_field'],kind,anchor,date)

def detect_gaps(plan, *, now=None):
    profile=plan.get('trip_profile',{}); gaps={}
    def add(category,field,entity,target,priority='HIGH',reason='Missing or unverified evidence',date=None,dependencies=None):
        value={'category':category,'required_field':field,'entity':entity,
            'travel_date':date or profile.get('start_date'),'criticality':priority,'reason':reason,
            'current_status':'NOT_RESEARCHED','researchable':True,'target':target,
            'dependencies':dependencies or [],'refresh_required':reason.startswith('REFRESH')}
        key=canonical_gap_id(value); gaps[key]={'gap_id':key,**value}
        return key
    for kind in ('hotel','flight'):
        if kind == 'flight' and profile.get('intercity_mode') == 'TRAIN': continue
        validation=plan.get('quote_validation',{}).get(kind,{})
        if validation.get('status')!='VERIFIED' or validation.get('refresh_required'):
            add(kind.upper()+'_EXACT_QUOTE','exact_quote',profile.get('hotel') if kind=='hotel' else profile.get('origin','')+' → '+profile.get('destination',''),
                {'kind':kind},'BLOCKING','REFRESH_RESEARCH_GAP' if validation.get('refresh_reason')=='EXPIRED' else 'Target-date full quote missing')
    hotel=plan.get('hotel_research',{})
    for field,category in HOTEL_FIELDS.items():
        if not hotel.get('field_evidence',{}).get(field) or freshness(hotel.get('field_evidence',{}).get(field,{}),'attraction_static',now=now)['refresh_required']:
            add(category,field,profile.get('hotel') or profile.get('lodging_area','hotel'),{'kind':'hotel','field':field})
    if profile.get('intercity_mode') != 'TRAIN' and not plan.get('flight_research',{}).get('field_evidence',{}).get('airport_pairs'):
        add('FLIGHT_ROUTE','airport_pairs',profile.get('origin','')+' → '+profile.get('destination',''),{'kind':'flight_static','field':'airport_pairs'})
    if profile.get('intercity_mode') != 'TRAIN' and not plan.get('flight_research',{}).get('field_evidence',{}).get('duration_reference'):
        add('FLIGHT_SCHEDULE','duration_reference',profile.get('origin','')+' → '+profile.get('destination',''),{'kind':'flight_static','field':'duration_reference'},'MEDIUM')
    attractions={a.get('name'):a for a in plan.get('attractions',[])}
    for day in plan.get('days',[]):
        graph=day.get('execution_graph',{}); nodes={n['id']:n for n in graph.get('nodes',[])}
        for n in nodes.values():
            if n['role']=='ACTIVITY':
                fields=n.get('field_evidence',{})
                for field,category in ATTRACTION_FIELDS.items():
                    old=fields.get(field,{})
                    if not old or freshness(old,'attraction_static',now=now)['refresh_required']:
                        add(category,field,n['place'],{'kind':'attraction','place_id':n['place_id'],'field':field},
                            'HIGH','REFRESH_RESEARCH_GAP' if old else 'Operation needs field-level opened-page proof')
                attractions.pop(n.get('place'),None)
            if n['role']=='MEAL':
                candidate=next((r for r in plan.get('restaurant_candidates',[]) if r.get('place_id')==n['place_id']),{})
                for field,category in RESTAURANT_FIELDS.items():
                    e=candidate.get('field_evidence',{}).get(field,{})
                    if not e or freshness(e,'attraction_static',now=now)['refresh_required']:
                        add(category,field,n.get('research_entity',n['place']),{'kind':'restaurant','place_id':n['place_id'],'field':field,
                              'date':day.get('date'),'area':day.get('area')},'HIGH')
                if not candidate.get('backup'):
                    add('RESTAURANT_STATIC','backup',n.get('research_entity',n['place']),{'kind':'restaurant','place_id':n['place_id'],'field':'backup','area':day.get('area')},'MEDIUM')
        for edge in graph.get('edges',[]):
            if edge.get('from_place_id')=='hotel' and edge.get('to_place_id') in {'kuromon','dotonbori','shinsaibashi'}:
                compared=[c for c in plan.get('candidate_comparisons',[]) if c.get('edge_id')==edge['id']]
                researched=plan.get('route_search_modes',{}).get(edge['from_place_id']+'->'+edge['to_place_id'],[])
                if not compared or len(compared[-1]['considered_options'])<2 or not {'DIRECT_WALK','PUBLIC_TRANSIT'}.issubset(researched):
                    a=nodes.get(edge['from_node'],{});b=nodes.get(edge['to_node'],{})
                    add('ROUTE','route_options',a.get('place','')+' → '+b.get('place',''),
                        {'kind':'route','edge_id':edge['id'],'date':day.get('date'),'from_place_id':a.get('place_id'),
                         'to_place_id':b.get('place_id'),'from':a.get('place'),'to':b.get('place')},'HIGH','Compare walk and public transit',day.get('date'))
            if route_evidence_valid(edge,nodes,now=now): continue
            a=nodes.get(edge['from_node'],{}); b=nodes.get(edge['to_node'],{})
            category='FLIGHT_SCHEDULE' if edge.get('purpose')=='flight' else 'AIRPORT_TRANSFER' if edge.get('purpose')=='airport_transfer' else 'ROUTE'
            deps=[identity('LOCATION',n.get('place_id')) for n in (a,b) if n.get('location_status')!='RESOLVED']
            add(category,'route',a.get('research_entity',a.get('place',''))+' → '+b.get('research_entity',b.get('place','')),
                {'kind':'route','edge_id':edge['id'],'date':day.get('date'),'from_place_id':a.get('place_id'),
                 'to_place_id':b.get('place_id'),'from':a.get('research_entity',a.get('place')),'to':b.get('research_entity',b.get('place'))},
                'BLOCKING' if edge.get('critical') else 'HIGH',
                'REFRESH_RESEARCH_GAP' if edge.get('checked_at') else 'Endpoint-specific route missing',day.get('date'),deps)
        if profile.get('walking_tolerance_steps') and not day.get('steps_basis'):
            add('WALKING_ACCESS','steps_basis',day.get('area','daily route'),{'kind':'walking','date':day.get('date')},'HIGH',date=day.get('date'))
    for a in attractions.values():
        if a['name'] not in profile.get('must_visit',[]):continue
        for field,category in ATTRACTION_FIELDS.items():
            if not a.get('field_evidence',{}).get(field):
                add(category,field,a['name'],{'kind':'attraction','name':a['name'],'field':field},'MEDIUM')
    for row in plan.get('cost_ledger',[]):
        if row.get('amount') is None and row.get('category') not in {'flight','hotel'}:
            if any(e['claim_type']=='cost_reference' and e['value'].get('category')==row.get('category') and not freshness(e,'attraction_static',now=now)['refresh_required'] for e in plan.get('research_evidence',[])):continue
            add('COST_REFERENCE','amount',row.get('category'),{'kind':'cost','row_id':row.get('id'),'category':row.get('category')},'MEDIUM')
    base=profile.get('destination_currency') or 'JPY'
    if base != profile.get('budget_currency','CNY') and not any(not freshness(r,'exchange',now=now)['refresh_required'] for r in plan.get('exchange_rates',[])):
        add('EXCHANGE_RATE','rate',base+' '+profile.get('budget_currency','CNY'),{'kind':'exchange','base_currency':base,'quote_currency':profile.get('budget_currency','CNY')},'MEDIUM')
    if not plan.get('weather_research'): add('WEATHER_REFERENCE','climate',profile.get('destination',''),{'kind':'weather'},'MEDIUM')
    if not profile.get('domestic_trip') and not plan.get('entry_research'): add('VISA_ENTRY_REQUIREMENT','entry',profile.get('destination',''),{'kind':'entry'},'HIGH')
    for conflict in plan.get('plan_qa',{}).get('findings',[]):
        add('ROUTE' if 'WALK' in conflict.get('code','') else 'COST_REFERENCE' if 'BUDGET' in conflict.get('code','') else 'ATTRACTION_STATIC',
            'alternative',conflict.get('reason','constraint conflict'),{'kind':'conflict','conflict':conflict},'BLOCKING')
    return list(gaps.values())
