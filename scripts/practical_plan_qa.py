"""Practical usefulness remains distinct from strict booking readiness."""
from decision_backfill import restaurant_fit
from reference_budget_estimator import estimate_budget
import re

def evaluate_practical(plan,*,now=None):
    checks=[];days=[]
    for day in plan.get('days',[]):
        nodes=day['execution_graph']['nodes'];closure=day.get('route_closure',{})
        meals=[]
        scheduled=[n for n in nodes if n['role'] in {'ACTIVITY','MEAL','REST'}]
        times=[re.match(r'^(\d{2}:\d{2})',str(n.get('time') or '')) for n in scheduled]
        sequence_ok=all(times) and [m[1] for m in times]==sorted(m[1] for m in times)
        for n in nodes:
            if n['role']=='MEAL':
                c=next((c for c in plan.get('restaurant_candidates',[]) if c.get('place_id')==n['place_id']),{})
                meals.append({'place':n['place'],'resolved':n['location_status']=='RESOLVED',**restaurant_fit(c,n,day)})
        days.append({'date':day['date'],'resolved_places':sum(n['location_status']=='RESOLVED' for n in nodes),'places':len(nodes),
            'movements_explained':closure.get('resolved_edges',0),'movements_required':closure.get('required_edges',0),
            'time_sequence_checked':sequence_ok,
            'walking_checked':bool(day.get('steps_basis') and isinstance(day.get('estimated_steps'),(int,float)) and day['estimated_steps']<=plan['trip_profile'].get('walking_tolerance_steps',float('inf'))),'meals':meals})
    budget=estimate_budget(plan,now=now)
    all_places=bool(days) and all(d['resolved_places']==d['places'] for d in days)
    all_routes=bool(days) and all(d['movements_explained']==d['movements_required'] for d in days)
    walking=all(d['walking_checked'] for d in days) if plan['trip_profile'].get('walking_tolerance_steps') else True
    constraints=not plan.get('plan_qa',{}).get('findings')
    checks=[{'check':'activities_selected','pass':bool(days)}, {'check':'places_resolved','pass':all_places},
        {'check':'major_movements_explained','pass':all_routes},{'check':'hard_constraints_checked','pass':constraints and walking},
        {'check':'restaurant_choices_useful','pass':all(m['status']=='FIT' for d in days for m in d['meals'])},
        {'check':'time_sequence_plausible','pass':bool(days) and all(d['time_sequence_checked'] for d in days)},
        {'check':'planning_cost_references','pass':budget['cost_reference_coverage']['ratio']>=.5},
        {'check':'unknowns_identified','pass':bool(plan.get('readiness'))}]
    status='NOT_READY' if not days or not constraints else 'READY' if all(c['pass'] for c in checks) else 'PARTIAL'
    return {'status':status,'checks':checks,'days':days,'booking_readiness':plan['readiness']['booking_readiness'],
        'planning_budget':budget['planning_budget'],'cost_reference_coverage':budget['cost_reference_coverage']}
