"""Query families, fair category allocation and explicit finite budgets."""
from collections import defaultdict
from research_ledger import identity

DEFAULT_LIMITS={'max_rounds':4,'max_queries_per_gap':6,'max_sources_per_gap':5,
    'max_total_queries':64,'max_total_opened_sources':96,'max_tasks_per_round':16}
def query_for(gaps, profile, attempt=0):
    from semantic_query_planner import semantic_query
    return semantic_query(gaps,profile,attempt)

def plan_tasks(gaps, ledger, profile, *, limits=None, remaining=None,plan=None,session=None):
    limits={**DEFAULT_LIMITS,**(limits or {})}; groups=defaultdict(list)
    for g in gaps:
        row=ledger.get(g['gap_id'],{}); attempts=len(row.get('attempts',[]))
        if row.get('final_status') in {'RESOLVED','CURRENT_REFERENCE_ONLY'} and g['required_field']!='route_options': continue
        cap=min(limits['max_queries_per_gap'],4 if 'EXACT' in g['category'] else 6 if g['criticality']=='BLOCKING' else 4 if g['criticality']=='HIGH' else 2)
        if attempts>=cap: continue
        kind=g['target']['kind']
        # Bundle operation fields for one entity; exact quotes remain independent.
        entity=tuple(sorted((str(g['target'].get('from_place_id')),str(g['target'].get('to_place_id'))))) if kind=='route' else g['entity']
        key=(kind,entity,'',g['required_field']=='exact_quote')
        groups[key].append(g)
    buckets=defaultdict(list)
    priority={'BLOCKING':0,'HIGH':1,'MEDIUM':2,'LOW':3}
    for values in groups.values():
        family=values[0]['target']['kind']
        if family=='route' and values[0]['category'] in {'AIRPORT_TRANSFER','FLIGHT_SCHEDULE'}: family=values[0]['category']
        buckets[family].append(values)
    for values in buckets.values(): values.sort(key=lambda gs:(min(priority[g['criticality']] for g in gs),bool(gs[0].get('dependencies')),len(ledger.get(gs[0]['gap_id'],{}).get('attempts',[])),gs[0].get('travel_date',''),gs[0]['entity']))
    # Reserve one task for each family before revisiting blocking quotes/routes.
    tasks=[]; task_cap=min(limits['max_tasks_per_round'],remaining if remaining is not None else limits['max_total_queries']);cap=len(groups)
    first_pass=True
    while any(buckets.values()) and len(tasks)<cap:
        for kind in sorted(buckets,key=lambda k:min(priority[g['criticality']] for gs in buckets[k] for g in gs) if buckets[k] else 9):
            weight={'route':3,'attraction':2}.get(kind,1) if first_pass else 1
            for _ in range(weight):
                if not buckets[kind] or len(tasks)>=cap: continue
                values=buckets[kind].pop(0); attempt=max(len(ledger.get(g['gap_id'],{}).get('attempts',[])) for g in values)
                from semantic_query_planner import semantic_query
                q=semantic_query(values,profile,attempt,plan)
                tasks.append({'task_id':identity([g['gap_id'] for g in values],attempt),'gap_ids':[g['gap_id'] for g in values],
                    'gaps':values,'attempt_index':attempt,'operation':'SEARCH_OPEN_EXTRACT','provider_order':
                    ['HOST_NATIVE_SEARCH','BROWSER_SEARCH','MCP_SEARCH','CUSTOM_SEARCH_API'],
                    'provider_class':(['OFFICIAL_BOOKING','OTA','INDEXED_SEARCH','OTA_SECONDARY'][min(attempt,3)] if 'EXACT' in values[0]['category'] else 'WEB_REFERENCE'),**q})
        first_pass=False
    from research_value_optimizer import optimize
    selected,suppressed=optimize(tasks,ledger,session)
    if session is not None:session.setdefault('suppressed_tasks',[]).extend(suppressed)
    # Reserve one high-value task per family, then use the remaining value ranking.
    families=set();fair=[]
    for t in selected:
        family=t['gaps'][0]['target']['kind']
        if family not in families and len(fair)<task_cap:fair.append(t);families.add(family)
    fair.extend(t for t in selected if t not in fair)
    return fair[:task_cap]
