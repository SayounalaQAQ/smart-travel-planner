"""Compare sourced alternatives; apply reversible planning decisions and revalidate."""
from copy import deepcopy
from research_ledger import identity,stamp
from research_backfill import compose_route
from data_freshness import freshness
import re

def opening_windows(value):
    text=str(value or '').replace('：',':')
    result=[]
    for a,b in re.findall(r'(\d{1,2}:\d{2})\s*[～〜~–-]\s*(?:翌)?(\d{1,2}:\d{2})',text):
        a=a.zfill(5);b=b.zfill(5)
        result.extend([(a,b)] if b>=a else [(a,'23:59'),('00:00',b)])
    return result

def address_key(value):
    return re.sub(r'大阪府|大阪市|中央区|丁目|番|号|[-\s]','',str(value or ''))

def apply_restaurant_decisions(out,now=None):
    decisions=[];changes=[]
    for day in out.get('days',[]):
        for node in day['execution_graph']['nodes']:
            if node['role']!='MEAL':continue
            slot=node.get('meal_slot_id',node['place_id'])
            options=[deepcopy(c) for c in out.get('restaurant_options',[]) if c.get('slot_id')==slot]
            if not options:continue
            evaluations=[]
            for c in options:
                c['time_windows']=opening_windows(c.get('opening_hours'))
                hotel=address_key(out['trip_profile'].get('hotel_address'))
                c['geographic_fit']=True if hotel and address_key(c.get('address'))==hotel else c.get('geographic_fit')
                fit=restaurant_fit(c,{**node,'time':node.get('time') or '12:30'},day)
                stale=any(freshness(e,'attraction_static',now=now)['refresh_required'] for e in c.get('field_evidence',{}).values())
                eligible=bool(c.get('name') and c.get('address') and fit['time_fit'] is True and fit['location_fit'] is True and not stale)
                evaluations.append({'candidate_id':c['candidate_id'],'eligible':eligible,'fit':fit,
                    'score':(0 if fit['time_fit'] else 1000)+(0 if fit['location_fit'] else 1000)+(10 if fit['queue_minutes'] is None else fit['queue_minutes'])+(20 if fit['price_fit'] is not True else 0)+(15 if c.get('route_fit') is not True else 0),
                    'reason':'Same published street address as hotel, lunch window fits planning 12:30; exact meal total/queue and floor access remain unknown' if eligible else 'Closed at meal time or geographic/operation proof incomplete'})
            eligible=sorted((v for v in evaluations if v['eligible']),key=lambda v:(v['score'],v['candidate_id']))
            selected=next((c for c in options if eligible and c['candidate_id']==eligible[0]['candidate_id']),None)
            prior=next((v for v in eligible if v['candidate_id']==node.get('selected_candidate_id')),None)
            if prior and prior['score']<=eligible[0]['score']*1.10:
                selected=next(c for c in options if c['candidate_id']==prior['candidate_id'])
            comparison={'decision_type':'RESTAURANT','slot_id':slot,'date':day['date'],'considered_options':options,
                'evaluations':evaluations,'selected_option':selected['candidate_id'] if selected else None,
                'rejected_options':[c['candidate_id'] for c in options if not selected or c['candidate_id']!=selected['candidate_id']],
                'selection_reason':'Prefer a researched lunch option at the hotel address; reject dinner-only candidates',
                'decision_status':'PROVISIONAL_SELECTION' if selected else 'NO_FEASIBLE_OPTION','confidence':'medium',
                'tradeoff':'Menu dish prices do not verify a lunch-set total; access/queue and target-day operation need recheck',
                'constraint_impact':'No early start or distant meal detour added; full-day walking remains unverified'}
            comparison['evidence']=[e['evidence_id'] for e in selected.get('field_evidence',{}).values()] if selected else []
            comparison['comparison_id']=identity(slot,[c['candidate_id'] for c in options],comparison['selected_option'])
            if not any(c.get('comparison_id')==comparison['comparison_id'] for c in out.get('candidate_comparisons',[])):
                out.setdefault('candidate_comparisons',[]).append(comparison)
            if not selected or node.get('selected_candidate_id')==selected['candidate_id']:continue
            evidence_ids=[e['evidence_id'] for e in selected.get('field_evidence',{}).values()]
            comparison['evidence']=evidence_ids;decisions.append(comparison)
            old=deepcopy(node)
            node.update(meal_slot_id=slot,place_id=selected['candidate_id'],place=selected['name'],address=selected['address'],
                opening_hours=selected['opening_hours'],time=node.get('time') or '12:30',location_status='RESOLVED',
                selected_candidate_id=selected['candidate_id'],planning_time_assumption=True)
            candidate={**selected,'place_id':selected['candidate_id']}
            if not any(c.get('place_id')==candidate['place_id'] for c in out.setdefault('restaurant_candidates',[])):out['restaurant_candidates'].append(candidate)
            for edge in day['execution_graph']['edges']:
                if node['id'] in (edge['from_node'],edge['to_node']):
                    side='from' if node['id']==edge['from_node'] else 'to'
                    edge[side+'_place_id']=node['place_id']
                    edge.update(status='UNAVAILABLE',mode='UNAVAILABLE',duration_minutes=None,fare=None,evidence_ids=[],failure_reason='Changed restaurant needs endpoint-specific route research')
                    for k in ('components','source_url','checked_at','selected_candidate_id','known_component_minutes','duration_complete','unknown_overhead'):edge.pop(k,None)
            if old.get('location_status')=='RESOLVED' and old.get('selected_candidate_id') and old['selected_candidate_id']!=selected['candidate_id']:
                rev={'old_decision':old,'new_decision':deepcopy(node),'trigger':'RESEARCH_DRIVEN_DECISION_CHANGE','evidence':evidence_ids,
                     'reason':comparison['selection_reason'],'impact':comparison['constraint_impact'],'date':day['date'],'checked_at':now or stamp()}
                out.setdefault('decision_revision_ledger',[]).append(rev);changes.append(rev)
    return decisions,changes

def route_candidates(edge,evidence,*,now=None):
    records=[e for e in evidence if e['claim_type']=='route_segment' and not freshness(e,'route',now=now)['refresh_required']]
    paths=[]
    def walk(at,parts,seen):
        if at==edge['to_place_id'] and parts:paths.append(parts);return
        if len(parts)>=4 or len(paths)>=16:return
        for e in records:
            v=e['value']
            if v['from_place_id']==at and v['to_place_id'] not in seen:walk(v['to_place_id'],parts+[e],seen|{v['to_place_id']})
    walk(edge['from_place_id'],[],{edge['from_place_id']})
    candidates=[];seen=set()
    for parts in paths:
        route=compose_route(edge,parts);eid=tuple(e['evidence_id'] for e in parts)
        if eid in seen:continue
        seen.add(eid);walks=[e['value'].get('duration_minutes') for e in parts if e['value']['mode']=='WALK']
        all_walk=all(e['value']['mode']=='WALK' for e in parts)
        fare_parts=[e['value'].get('fare') for e in parts];currencies={e['value'].get('currency') for e in parts if e['value'].get('fare') is not None}
        candidates.append({'candidate_id':identity(eid),'decision_type':'ROUTE','from_place_id':edge['from_place_id'],
            'to_place_id':edge['to_place_id'],'route':route,'mode':route['mode'],
            'total_minutes':route['duration_minutes'],'walking_minutes':sum(walks) if walks and all(x is not None for x in walks) else None,
            'fare':sum(fare_parts) if all(x is not None for x in fare_parts) and len(currencies)==1 else None,
            'currency':next(iter(currencies)) if len(currencies)==1 else None,
            'transfers':max(0,len([e for e in parts if e['value']['mode']!='WALK'])-1),
            'waiting_uncertainty':not all_walk,'unknown_components':route.get('unknown_overhead',[]),
            'evidence_ids':list(eid),'source_tiers':[e.get('tier',4) for e in parts],
            'distance_meters':parts[0]['value'].get('distance_meters') if len(parts)==1 else None,
            'weather_dependency':'outdoor_walk' if all_walk else 'partly_outdoor'})
    return candidates

def compare_routes(candidates,profile):
    evaluations=[]
    for c in candidates:
        walks=c.get('walking_minutes');total=c.get('total_minutes')
        # Unknown walking is penalized, never implicitly zero. Minutes are not steps.
        blocked=bool(c.get('hard_constraint_violations'))
        score=(1000 if blocked else 0)+(30 if walks is None else walks)+(12*c.get('transfers',0))
        score+=8 if c.get('waiting_uncertainty') else 0
        score+=12 if total is None else total*.2
        score+=max(c.get('source_tiers') or [4])*2
        score+=3 if c.get('fare') is None else min(3,c['fare']/1000)
        if profile.get('weather_condition') in {'heavy_rain','extreme_heat'} and c['mode']=='WALK':score+=25
        evaluations.append({'candidate_id':c['candidate_id'],'score':round(score,2),'blocked':blocked,
            'dimensions':{'walking_minutes':walks,'total_minutes':total,'fare':c.get('fare'),
                'transfers':c.get('transfers'),'waiting_uncertainty':c.get('waiting_uncertainty'),
                'known_hard_conflicts_checked':not blocked,'day_steps_checked':False},
            'reason':'Protect walking load, fewer transfers, known boundaries and reference reliability; unknown costs remain unknown'})
    allowed=sorted((r for r in evaluations if not r['blocked']),key=lambda r:r['score'])
    selected=allowed[0]['candidate_id'] if allowed else None
    evidence=next((c['evidence_ids'] for c in candidates if c['candidate_id']==selected),[])
    return {'decision_type':'ROUTE','considered_options':deepcopy(candidates),'evaluations':evaluations,'selected_option':selected,
        'rejected_options':[c['candidate_id'] for c in candidates if c['candidate_id']!=selected],
        'selection_reason':'Lower combined walking/complexity/uncertainty score; not a trained utility probability',
        'decision_status':'PROVISIONAL_SELECTION' if selected else 'NO_FEASIBLE_OPTION',
        'tradeoff':'Current references are not 2027 schedules; complete daily steps and fares may still be unknown',
        'constraint_impact':'Budget cap, dates and sleep preference preserved; hard walking compliance not claimed without daily distances',
        'confidence':'medium' if selected else 'low','evidence':list(evidence)}

def restaurant_fit(candidate,node,day):
    opening=candidate.get('time_windows') or opening_windows(candidate.get('opening_hours'));time=str(node.get('time') or '')[:5]
    time_fit=any(a<=time<=b for a,b in opening) if opening and time else None
    location_fit=candidate.get('geographic_fit') # Explicit host-inspected area proof, not name similarity.
    return {'time_fit':time_fit,'location_fit':location_fit,'queue_minutes':candidate.get('queue_minutes'),
            'price_fit':candidate.get('price_fit'),'backup_is_required_stop':False,
            'status':'REJECT' if time_fit is False or location_fit is False else 'FIT' if time_fit is True and location_fit is True and candidate.get('price_fit') is True and candidate.get('route_fit') is True else 'PARTIAL'}

def apply_decisions(plan,*,now=None):
    out=deepcopy(plan);records=out.get('research_evidence',[]);decisions,changes=apply_restaurant_decisions(out,now)
    for day in out.get('days',[]):
        graph=day['execution_graph']
        for edge in graph['edges']:
            candidates=route_candidates(edge,records,now=now)
            if not candidates:continue
            comparison=compare_routes(candidates,out['trip_profile']);comparison.update(edge_id=edge['id'],date=day['date'])
            selected=next((c for c in candidates if c['candidate_id']==comparison['selected_option']),None)
            if not selected:continue
            previous=edge.get('selected_candidate_id')
            old_eval=next((v for v in comparison['evaluations'] if v['candidate_id']==previous),None)
            best_eval=next(v for v in comparison['evaluations'] if v['candidate_id']==selected['candidate_id'])
            if old_eval and old_eval['score']<=best_eval['score']*1.10:
                selected=next(c for c in candidates if c['candidate_id']==previous)
                comparison.update(selected_option=previous,evidence=selected['evidence_ids'],
                    rejected_options=[c['candidate_id'] for c in candidates if c['candidate_id']!=previous],
                    selection_reason='Retain previous feasible selection within 10% of current best; avoid immaterial revision')
            signature=identity(edge['id'],[c['candidate_id'] for c in candidates],comparison['selected_option'])
            comparison['comparison_id']=signature
            if not any(c.get('comparison_id')==signature for c in out.get('candidate_comparisons',[])):
                out.setdefault('candidate_comparisons',[]).append(deepcopy(comparison))
            old=edge.pop('research_prior_route',None) or {k:deepcopy(edge.get(k)) for k in ('mode','status','duration_minutes','components','operator','line','evidence_ids')}
            if previous==selected['candidate_id']:continue
            for key in ('components','known_component_minutes','duration_complete','unknown_overhead'):
                if key not in selected['route']:edge.pop(key,None)
            edge.update(selected['route']);edge['selected_candidate_id']=selected['candidate_id']
            comparison['evidence']=selected['evidence_ids'];decisions.append(comparison)
            old_path=[(c['from_place_id'],c['to_place_id']) for c in old.get('components') or []]
            new_path=[(c['from_place_id'],c['to_place_id']) for c in edge.get('components') or []]
            material=old['mode'] not in {None,'UNAVAILABLE'} and (old['mode']!=edge['mode'] or bool(old_path and new_path and old_path!=new_path))
            if material:
                revision={'old_decision':old,'new_decision':deepcopy(selected),'trigger':'RESEARCH_DRIVEN_DECISION_CHANGE',
                    'evidence':selected['evidence_ids'],'reason':comparison['selection_reason'],'impact':comparison['constraint_impact'],
                    'edge_id':edge['id'],'date':day['date'],'checked_at':now or stamp()}
                out.setdefault('decision_revision_ledger',[]).append(revision);changes.append(revision)
    out.setdefault('research_decision_ledger',[]).extend(decisions)
    # Existing evaluator includes conflict detection, cost and canonical graph projections.
    from execution_readiness import evaluate_plan
    out=evaluate_plan(out,now=now)
    out['targeted_replanning_required']=bool(out['plan_qa']['findings'])
    from research_gap_detector import detect_gaps
    out['targeted_replanning_tasks']=[g for g in detect_gaps(out,now=now) if g['target']['kind']=='conflict']
    return out,changes
