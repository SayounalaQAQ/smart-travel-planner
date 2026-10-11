"""Evidence-only writes to canonical graph plus derived compatibility views."""
from copy import deepcopy
from source_ranker import select_evidence
from execution_graph import project_graph
from data_freshness import freshness

def compose_route(edge, segments, *, max_parts=4):
    """Endpoint identity must connect. Unknown overhead never becomes numeric duration."""
    start=edge['from_place_id']; end=edge['to_place_id']; paths=[]
    def walk(at,parts,seen):
        if at==end and parts: paths.append(parts); return
        if len(parts)>=max_parts: return
        for segment in segments:
            v=segment['value']
            if v['from_place_id']==at and v['to_place_id'] not in seen:
                walk(v['to_place_id'],parts+[segment],seen|{v['to_place_id']})
    walk(start,[],{start})
    if not paths: return None
    parts=min(paths,key=lambda p:(len(p),sum(s['value'].get('duration_minutes') or 1000 for s in p)))
    known=[s['value'].get('duration_minutes') for s in parts]
    if len(parts)==1 and known[0] is not None and not parts[0]['value'].get('reversed'):
        s=parts[0]; v=s['value']
        return {'mode':v['mode'],'status':'CURRENT_REFERENCE','duration_minutes':known[0],
            'source_url':s['source_url'],'checked_at':s['retrieved_at'],'operator':v.get('operator'),
            'line':v.get('line'),'evidence_ids':[s['evidence_id']],'fare':None,
            'boundary':v['boundary'],'applicable_date':s['applicable_date'],'failure_reason':None}
    return {'status':'COMPOSITE_REFERENCE','mode':'WALK' if all(s['value']['mode']=='WALK' for s in parts) else 'TRAIN',
        'duration_minutes':None,'fare':None,'checked_at':min(s['retrieved_at'] for s in parts),
        'source_url':parts[0]['source_url'],'operator':'Multiple source references','line':'See components',
        'evidence_ids':[s['evidence_id'] for s in parts],
        'components':[{'from_place_id':s['value']['from_place_id'],'to_place_id':s['value']['to_place_id'],
            'mode':s['value']['mode'],'duration_minutes':s['value'].get('duration_minutes'),
            'boundary':s['value']['boundary'],'source_url':s['source_url'],'checked_at':s['retrieved_at'],
            'evidence_id':s['evidence_id'],'limitations':s['value'].get('limitations',[])} for s in parts],
        'known_component_minutes':sum(x for x in known if x is not None),
        'duration_complete':False,'unknown_overhead':['station exits/concourse connection','waiting/transfer if used','reverse-direction walking estimate if used'],
        'applicable_date':'CURRENT_OPERATION','failure_reason':None}

def backfill(plan,evidence,*,now=None):
    out=deepcopy(plan); changes=[]; conflicts=[]
    all_records=out.setdefault('research_evidence',[])
    seen={e['evidence_id'] for e in all_records}
    incoming={e['evidence_id']:e for e in evidence}
    for i,record in enumerate(all_records):
        if record['evidence_id'] in incoming: all_records[i]=deepcopy(incoming[record['evidence_id']])
    all_records.extend(e for e in evidence if e['evidence_id'] not in seen)
    groups={}
    for e in all_records:
        kind='route' if e['claim_type']=='route_segment' else 'exchange' if e['claim_type']=='rate' else 'attraction_static'
        if freshness(e,kind,now=now)['refresh_required']: continue
        key=(str(e['target']),e['claim_type'],e['subject'])
        if e['claim_type']=='cost_reference':key=key+(e['value']['item'],e['value']['scope'])
        groups.setdefault(key,[]).append(e)
    for records in groups.values():
        e,issues=select_evidence(records); conflicts.extend(issues)
        if not e or e['claim_type']=='route_segment': continue
        target=e['target']; kind=target.get('kind'); field=e['claim_type']; value=e['value']
        if kind=='restaurant_option':
            options=out.setdefault('restaurant_options',[])
            obj=next((r for r in options if r.get('candidate_id')==target.get('candidate_id')),None)
            if obj is None:
                obj={'candidate_id':target['candidate_id'],'slot_id':target['place_id']};options.append(obj)
            targets=[obj]
        elif field=='exact_quote':
            quote=deepcopy(value); quote.update(source_url=e['source_url'],checked_at=e['retrieved_at'])
            label='hotel' if target.get('kind')=='hotel' else 'flight'
            out.setdefault(label+'_availability',[]).append(quote)
            out['trip_profile'][label+'_quote_id']=quote['quote_id']; targets=[]
        elif kind=='attraction':
            targets=[n for d in out.get('days',[]) for n in d['execution_graph']['nodes'] if n['role']=='ACTIVITY' and
                     (n['place_id']==target.get('place_id') or n['place']==target.get('name'))]
            places={n.get('place') for n in targets}
            targets.extend(a for a in out.get('attractions',[]) if a.get('name')==e['subject'] or a.get('name')==target.get('name') or a.get('name') in places)
        elif kind=='restaurant':
            candidates=out.setdefault('restaurant_candidates',[])
            obj=next((r for r in candidates if r.get('place_id')==target.get('place_id')),None)
            if obj is None: obj={'place_id':target.get('place_id')}; candidates.append(obj)
            targets=[obj]
        elif kind in {'hotel','flight_static','weather','entry'}:
            key={'hotel':'hotel_research','flight_static':'flight_research','weather':'weather_research','entry':'entry_research'}[kind]
            targets=[out.setdefault(key,{})]
        elif kind=='exchange' and field=='rate':
            base=target.get('base_currency'); quote=target.get('quote_currency')
            if base and quote and isinstance(value,(int,float)) and not isinstance(value,bool) and value>0:
                rates=out.setdefault('exchange_rates',[])
                rates[:]=[r for r in rates if (r.get('base_currency'),r.get('quote_currency'))!=(base,quote)]
                rates.append({'base_currency':base,'quote_currency':quote,'rate':value,'source_url':e['source_url'],
                              'checked_at':e['retrieved_at'],'evidence_id':e['evidence_id']})
                changes.append({'kind':'exchange','field':'rate','new':value,'evidence_id':e['evidence_id']})
            targets=[]
        else: targets=[]
        for obj in targets:
            prior=obj.get(field); obj[field]=value; obj.setdefault('field_evidence',{})[field]=deepcopy(e)
            obj.update(source_url=e['source_url'],source_checked_at=e['retrieved_at'],checked_at=e['retrieved_at'])
            if prior!=value: changes.append({'kind':kind,'field':field,'old':prior,'new':value,'evidence_id':e['evidence_id']})
        if kind=='hotel' and field=='address' and e['subject']==out['trip_profile'].get('hotel'):
            out['trip_profile']['hotel_address']=value
            for d in out.get('days',[]):
                for n in d['execution_graph']['nodes']:
                    if n['role']=='HOTEL' and n['place']==e['subject']: n.update(address=value,location_status='RESOLVED')
    for candidate in out.get('restaurant_candidates',[]):
        if not candidate.get('name') or not candidate.get('address'): continue
        for d in out.get('days',[]):
            for n in d['execution_graph']['nodes']:
                if n['role']=='MEAL' and n['place_id']==candidate['place_id']:
                    n.setdefault('research_entity',n['place'])
                    n.update(place=candidate['name'],location_status='RESOLVED',address=candidate['address'],
                        opening_hours=candidate.get('opening_hours'),cuisine=candidate.get('cuisine'),
                        backup=candidate.get('backup'),restaurant_source=candidate.get('source_url'))
    segments=[e for e in all_records if e['claim_type']=='route_segment' and not freshness(e,'route',now=now)['refresh_required']]
    for d in out.get('days',[]):
        graph=d['execution_graph']; nodes={n['id']:n for n in graph['nodes']}
        for n in nodes.values():
            if n.get('role')=='ACTIVITY':
                n['operations_checked']=all(n.get('field_evidence',{}).get(f) and not freshness(n['field_evidence'][f],'attraction_static',now=now)['refresh_required'] for f in ('opening_hours','ticket_price','reservation_required','transport_info'))
        for edge in graph['edges']:
            if edge.get('status')=='VERIFIED': continue
            if edge.get('selected_candidate_id'): continue
            if any(nodes[k]['location_status']!='RESOLVED' for k in (edge['from_node'],edge['to_node'])): continue
            route=compose_route(edge,segments)
            if route and route!= {k:edge.get(k) for k in route}:
                edge.setdefault('research_prior_route',{k:deepcopy(edge.get(k)) for k in ('mode','status','duration_minutes','components','operator','line','evidence_ids')})
                changes.append({'kind':'route','edge_id':edge['id'],'old':edge['status'],'new':route['status'],'evidence_ids':route['evidence_ids']})
                edge.update(route)
        project_graph(d)
    for attraction in out.get('attractions',[]): attraction['research_audited']=True
    if out.get('weather_research',{}).get('climate'): out['weather_data_status']='HISTORICAL_REFERENCE'
    # Known partial menu/static facts do not close an entire trip cost category.
    for row in out.get('cost_ledger',[]):
        related=[e for e in all_records if e['target'].get('kind')=='cost' and e['target'].get('row_id')==row.get('id') and e['claim_type']=='amount']
        if related:
            e=related[-1]
            if e.get('unit')==row.get('currency') and isinstance(e['value'],(int,float)):
                row.update(amount=e['value'],source=e['source_url'],checked_at=e['retrieved_at'],cost_type='CURRENT_REFERENCE')
    out['research_source_conflicts']=conflicts
    out.setdefault('research_backfill_ledger',[]).extend(changes)
    return out,changes
