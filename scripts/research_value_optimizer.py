"""Transparent heuristics, deduplication and expiring provider-class breakers."""
from datetime import timedelta
from data_freshness import timestamp
from research_ledger import stamp

WEIGHTS={'blocking':3,'usefulness':4,'information_gain':2,'reuse':3,'success':2,'retry_cost':3,'uncertainty':2}
BREAK_REASONS={'BOOKING_FORM_ONLY','DYNAMIC_INVENTORY_INACCESSIBLE','PROVIDER_UNAVAILABLE'}

def research_value(task,ledger,weights=None):
    w={**WEIGHTS,**(weights or {})};gaps=task['gaps'];attempt=max((len(ledger.get(g['gap_id'],{}).get('attempts',[])) for g in gaps),default=0)
    need=task.get('intent',{}).get('information_need','');exact=need.startswith('EXACT_')
    dimensions={'blocking':int(any(g['criticality']=='BLOCKING' for g in gaps)),
        'usefulness':3 if any(g['target']['kind']=='route' for g in gaps) else 2 if any(g['target']['kind'] in {'restaurant','attraction','cost','hotel'} for g in gaps) else 1,
        'information_gain':min(4,len(gaps)),'reuse':min(4,len({g.get('travel_date') for g in gaps})+int(any(g['target']['kind']=='hotel' for g in gaps))),
        'success':1 if exact else 3,'retry_cost':attempt,'uncertainty':2 if exact else 0}
    score=sum(w[k]*v*(-1 if k in {'retry_cost','uncertainty'} else 1) for k,v in dimensions.items())
    if any(g.get('required_field')=='route_options' for g in gaps):score+=20
    return {'score':score,'dimensions':dimensions,'weights':w,'kind':'HEURISTIC_NOT_PROBABILITY'}

def query_key(query):return ' '.join(query.casefold().split())

def record_breaker(session,task,response):
    reason=response.get('failure_code');provider_class=response.get('provider_class') or task.get('provider_class')
    if reason not in BREAK_REASONS or not provider_class:return
    now=timestamp(response['executed_at']); key=task['intent']['entity_type']+':'+provider_class
    record=session.setdefault('provider_breakers',{}).setdefault(key,{'failures':0})
    if record.get('blocked_until') and timestamp(record['blocked_until'])<=now:
        record['failures']=0
    if record.get('reason') not in {None,reason}:record['failures']=0
    record.update(failures=record['failures']+1,reason=reason,checked_at=response['executed_at'],
        blocked_until=(now+timedelta(hours=6)).isoformat(),scope='PROVIDER_CLASS_AND_ENTITY_TYPE')

def blocked(session,task,now=None):
    key=task.get('intent',{}).get('entity_type','')+':'+task.get('provider_class','')
    row=session.get('provider_breakers',{}).get(key)
    return bool(row and row['failures']>=2 and timestamp(row['blocked_until'])>timestamp(now or stamp()))

def optimize(tasks,ledger,session=None,now=None):
    session=session or {};clock=timestamp(now or stamp())
    seen={query_key(q['query']) for q in session.get('query_audit',[]) if clock-timestamp(q['executed_at'])<timedelta(hours=6)};selected=[];suppressed=[]
    for task in tasks:
        key=query_key(task['query'])
        if task.get('quality_gate',{}).get('status')!='PASS':reason='QUERY_QUALITY_GATE'
        elif blocked(session,task,now):reason='PROVIDER_CLASS_BLOCKED'
        elif key in seen:reason='DUPLICATE_QUERY'
        else:
            seen.add(key);task['research_value']=research_value(task,ledger,session.get('value_weights'));selected.append(task);continue
        suppressed.append({'task_id':task['task_id'],'query':task['query'],'reason':reason})
    return sorted(selected,key=lambda t:-t['research_value']['score']),suppressed

def stop_policy(session,tasks):
    if session['queries_executed']>=session['limits']['max_total_queries'] or session['sources_opened']>=session['limits']['max_total_opened_sources'] or session['round']>=session['limits']['max_rounds']:return 'GLOBAL_BUDGET_EXHAUSTED'
    if session.get('available_capabilities')==[]:return 'NO_AVAILABLE_CAPABILITY'
    if tasks:
        recent=session.get('recent_rounds',[])[-2:]
        if len(recent)==2 and all(r['new_information_queries']==0 for r in recent) and not any(t['research_value']['score']>=30 for t in tasks):return 'DIMINISHING_RETURNS'
        return None
    if any(r['reason']=='PROVIDER_CLASS_BLOCKED' for r in session.get('suppressed_tasks',[])):return 'PROVIDER_CLASS_BLOCKED'
    if any(r['reason']=='DUPLICATE_QUERY' for r in session.get('suppressed_tasks',[])):return 'DIMINISHING_RETURNS'
    return 'ALL_HIGH_VALUE_GAPS_RESOLVED' if all(r['final_status'] in {'RESOLVED','CURRENT_REFERENCE_ONLY'} for r in session['ledger'].values()) else 'DIMINISHING_RETURNS'
