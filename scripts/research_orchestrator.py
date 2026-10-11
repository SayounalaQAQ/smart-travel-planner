#!/usr/bin/env python3
"""Resumable host research protocol. init -> next -> host executes -> consume -> next.

The host performs actual search/open/semantic extraction using its permitted tools.
This script never fabricates a search and never marks an issued request as executed.
ProviderChain.run_round is an alternative for environments with Python callbacks.
"""
import argparse
import json
from copy import deepcopy
from pathlib import Path
from research_gap_detector import detect_gaps
from research_planner import DEFAULT_LIMITS, plan_tasks
from research_ledger import entry, finish, stamp
from evidence_extractor import extract_evidence
from research_backfill import backfill
from research_coverage import coverage,cost_coverage
from execution_readiness import evaluate_plan
from execution_graph import route_evidence_valid
from research_value_optimizer import optimize,record_breaker,stop_policy
from decision_backfill import apply_decisions
from reference_budget_estimator import estimate_budget
from practical_plan_qa import evaluate_practical

def start(plan, *, limits=None, now=None):
    configured=json.loads((Path(__file__).resolve().parents[1]/'config/defaults.json').read_text(encoding='utf-8')).get('research',{})
    limits={**DEFAULT_LIMITS,**configured,**(limits or {})}
    for k,v in limits.items():
        if not isinstance(v,int) or isinstance(v,bool) or v<1 or v>DEFAULT_LIMITS[k]:
            raise ValueError('Research limits may only reduce default caps')
    out=evaluate_plan(plan,now=now); gaps=detect_gaps(out,now=now)
    return {'schema_version':'0.9.3','plan':out,'initial_gaps':deepcopy(gaps),'gaps':gaps,
        'ledger':{g['gap_id']:entry(g) for g in gaps},'limits':limits,'round':0,
        'issued':[],'consumed':[],'queries_executed':0,'sources_opened':0,
        'completion':'NOT_STARTED','initial_route_closure':deepcopy(out['route_closure']),
        'raw_captures':[],'rejected_claims':[],'user_questions':[],'query_audit':[],
        'provider_breakers':{},'suppressed_tasks':[],'value_weights':json.loads((Path(__file__).resolve().parents[1]/'config/defaults.json').read_text(encoding='utf-8')).get('research_value_weights',{}),
        'refresh_triggers':['provider capability changes','before departure recheck current operation','scheduled checkpoint if host explicitly schedules it']}

def settle_pending(session):
    """An unexecuted/retired task is not a failed search at the stop boundary."""
    active={gid for task in session.get('issued',[]) for gid in task['gap_ids']}
    for gid,row in session['ledger'].items():
        if row['final_status']=='RESEARCH_PENDING' and gid not in active:
            row['final_status']='NOT_RESEARCHED' if not row['attempts'] else 'PARTIAL_DATA' if row['evidence_ids'] else 'SOURCE_UNAVAILABLE'

def issue(session):
    if session['issued']: return deepcopy(session['issued'])
    limits=session['limits']
    if session['round']>=limits['max_rounds'] or session['queries_executed']>=limits['max_total_queries'] or session['sources_opened']>=limits['max_total_opened_sources']:
        session['completion']='EXHAUSTED';session['stop_reason']='GLOBAL_BUDGET_EXHAUSTED';settle_pending(session); return []
    tasks=plan_tasks(session['gaps'],session['ledger'],session['plan']['trip_profile'],limits=limits,
        remaining=limits['max_total_queries']-session['queries_executed'],plan=session['plan'],session=session)
    stop=stop_policy(session,tasks)
    if tasks and stop:
        session['completion']='EXHAUSTED';session['stop_reason']=stop;settle_pending(session);return []
    if not tasks:
        session['completion']='COMPLETE' if all(r['final_status'] in {'RESOLVED','CURRENT_REFERENCE_ONLY'} for r in session['ledger'].values()) else 'EXHAUSTED'
        session['stop_reason']=stop_policy(session,tasks)
        settle_pending(session)
        return []
    # Every issued task gets an actual source allowance before host execution.
    allowance=limits['max_total_opened_sources']-session['sources_opened']
    tasks=tasks[:allowance]
    for i,task in enumerate(tasks):
        task['max_sources']=min(limits['max_sources_per_gap'],max(1,allowance//(len(tasks)-i)))
        allowance-=task['max_sources']
    session['issued']=tasks; session['completion']='IN_PROGRESS'
    for task in tasks:
        for gid in task['gap_ids']: session['ledger'][gid]['final_status']='RESEARCH_PENDING'
    return deepcopy(tasks)

def consume(session,responses,*,now=None):
    tasks={t['task_id']:t for t in session['issued']}
    ids=[r.get('task_id') for r in responses]
    if len(ids)!=len(set(ids)) or any(i not in tasks or i in session['consumed'] for i in ids):
        raise ValueError('Unknown or duplicate response; no attempt recorded')
    if session['sources_opened']+sum(len(r.get('pages',[])) for r in responses)>session['limits']['max_total_opened_sources']:
        raise ValueError('Opened source budget exceeded')
    # Validate entire batch before mutation (atomic input contract).
    parsed=[]
    for response in responses:
        task=tasks[response['task_id']]
        if len(response.get('pages',[]))>tasks[response['task_id']].get('max_sources',session['limits']['max_sources_per_gap']):
            raise ValueError('Per-task source budget exceeded')
        if not response.get('executed_at') or response.get('executed') is not True:
            raise ValueError('Issued task is not an executed attempt')
        parsed.append((task,response,*extract_evidence(task,response,now=now)))
    for task,response,evidence,rejected in parsed:
        session['queries_executed']+=1; session['sources_opened']+=len(response.get('pages',[]))
        session.setdefault('query_audit',[]).append({'task_id':task['task_id'],'query':task['query'],
            'round':session['round']+1,
            'intent':task.get('intent'),'quality_gate':task.get('quality_gate'),'research_value':task.get('research_value'),
            'provider_class':task.get('provider_class'),'executed_at':response['executed_at'],
            'observed_failure_class':response.get('provider_class'),
            'candidate_exclusions':[x for x in response.get('candidate_exclusions',[]) if x.get('reason') and any(p.get('status')=='OPENED' and p['url']==x.get('source_url') for p in response.get('pages',[]))],
            'accepted_evidence_ids':[e['evidence_id'] for e in evidence],
            'new_evidence_ids':[e['evidence_id'] for e in evidence if e['evidence_id'] not in {old['evidence_id'] for old in session['plan'].get('research_evidence',[])}],
            'failure_code':response.get('failure_code'),'raw_artifact':response.get('raw_artifact')})
        record_breaker(session,task,response)
        for g in task['gaps']:
            target=g['target'];need=task.get('intent',{}).get('information_need')
            if target.get('kind')=='route' and need in {'DIRECT_WALK','PUBLIC_TRANSIT'}:
                key=str(target.get('from_place_id'))+'->'+str(target.get('to_place_id'))
                modes=session['plan'].setdefault('route_search_modes',{}).setdefault(key,[])
                if need not in modes:modes.append(need)
        session['consumed'].append(task['task_id']); session['rejected_claims'].extend(rejected)
        attempt={'task_id':task['task_id'],'query':task['query'],'query_class':task['query_class'],
            'language':task['language'],'provider':response.get('provider'),
            'provider_attempts':response.get('provider_attempts',[]),'checked_at':response['executed_at'],
            'result':'OPENED_PAGE_REFERENCE' if evidence else 'SOURCE_FOUND_NO_SUPPORTED_FACT' if response.get('pages') else 'PROVIDER_UNAVAILABLE' if not response.get('results') else 'SOURCE_UNAVAILABLE',
            'opened_urls':[p['url'] for p in response.get('pages',[]) if p.get('status')=='OPENED'],
            'failed_sources':[{'url':p.get('url'),'reason':p.get('failure_reason')} for p in response.get('pages',[]) if p.get('status')!='OPENED'],
            'search_result_urls':[r.get('url') for r in response.get('results',[])],
            'failure_reason':response.get('failure_reason'),'raw_artifact':response.get('raw_artifact')}
        session['raw_captures'].append(response.get('raw_artifact'))
        for gid in task['gap_ids']:
            row=session['ledger'][gid]; row['attempts'].append(deepcopy(attempt))
            relevant=[e['evidence_id'] for e in evidence if e['claim_type']==next(g['required_field'] for g in task['gaps'] if g['gap_id']==gid)]
            row['evidence_ids']=list(dict.fromkeys(row['evidence_ids']+relevant))
            category=row['category']
            status='PARTIAL_DATA' if evidence else 'EXACT_DATE_UNAVAILABLE' if 'EXACT_QUOTE' in category else 'SOURCE_UNAVAILABLE' if response.get('results') else 'PROVIDER_UNAVAILABLE'
            finish(row,status,'No matching opened-page fact returned' if not evidence else 'Partial entity evidence')
        session['plan'],_=backfill(session['plan'],evidence,now=now)
    session['issued']=[t for t in session['issued'] if t['task_id'] not in ids]
    if not session['issued']:
        settle_pending(session)
        session['round']+=1
        rows=[r for r in session.get('query_audit',[]) if r.get('round')==session['round']]
        useful=sum(bool(r['new_evidence_ids'] or r.get('candidate_exclusions')) for r in rows)
        session.setdefault('recent_rounds',[]).append({'round':session['round'],'queries':len(rows),'new_information_queries':useful,'yield':useful/len(rows) if rows else 0})
    session['plan'],_=apply_decisions(session['plan'],now=now)
    refresh(session,now=now)
    return session

def refresh(session,*,now=None):
    session['plan']=evaluate_plan(session['plan'],now=now)
    session['plan']['reference_budget']=estimate_budget(session['plan'],now=now)
    session['plan']['practical_plan_readiness']=evaluate_practical(session['plan'],now=now)
    # Evidence can resolve dependencies and multiple equivalent edges without repeat search.
    remaining=detect_gaps(session['plan'],now=now); remaining_ids={g['gap_id'] for g in remaining}
    for g in remaining:
        if g['gap_id'] not in session['ledger']:
            session['ledger'][g['gap_id']]=entry(g); session['gaps'].append(g)
    for gap in session['gaps']:
        row=session['ledger'][gap['gap_id']]
        if gap['gap_id'] not in remaining_ids:
            target=gap['target']; source_ids=[]
            if target.get('kind')=='route':
                edge=next((e for d in session['plan']['days'] for e in d['execution_graph']['edges'] if e['id']==target.get('edge_id')),{})
                source_ids=edge.get('evidence_ids',[])
            else:
                source_ids=[e['evidence_id'] for e in session['plan'].get('research_evidence',[]) if e['claim_type']==gap['required_field'] and
                            (e['subject']==gap['entity'] or e['target'].get('place_id')==target.get('place_id') and target.get('place_id'))]
                if target.get('kind')=='cost':source_ids=[e['evidence_id'] for e in session['plan'].get('research_evidence',[]) if e['claim_type']=='cost_reference' and e['value']['category']==target.get('category')]
            row['evidence_ids']=list(dict.fromkeys(row['evidence_ids']+source_ids))
            if not row['attempts']:
                # Dependency resolution must carry the real producing task audit.
                task_ids={e['task_id'] for e in session['plan'].get('research_evidence',[]) if e['evidence_id'] in source_ids}
                for other in session['ledger'].values():
                    match=next((a for a in other['attempts'] if a['task_id'] in task_ids),None)
                    if match:
                        row['attempts'].append({**deepcopy(match),'result':'DEPENDENCY_BACKFILL'}); break
            if row['attempts'] and row['evidence_ids']:
                row['final_status']='CURRENT_REFERENCE_ONLY'
                row['failure_reason']=None
    session['plan']['research_coverage']=coverage(session['gaps'],session['ledger'])
    session['plan']['cost_research_coverage']=cost_coverage(session['plan'],session['gaps'],session['ledger'])
    session['plan']['research_attempt_ledger']=list(session['ledger'].values())
    session['plan']['research_completion']='IN_PROGRESS' if session['issued'] else 'PARTIAL'
    session['completion']=session['plan']['research_completion']
    return session

def reextract(session,tasks,responses,*,now=None):
    """Correct extraction of existing captures without inventing another search attempt."""
    lookup={t['task_id']:t for t in tasks}
    for r in responses:
        task=lookup[r['task_id']]
        attempts=[a for row in session['ledger'].values() for a in row['attempts'] if a['task_id']==r['task_id']]
        if r['task_id'] not in session['consumed'] or not attempts or any(a['query']!=r['query'] for a in attempts):
            raise ValueError('Re-extraction requires actual consumed query audit')
        opened=set(attempts[0]['opened_urls'])
        if any(p['url'] not in opened for p in r.get('pages',[]) if p.get('status')=='OPENED'):
            raise ValueError('Cannot add unexecuted page opens during re-extraction')
        for a in attempts:
            if a['checked_at']!=r['executed_at']:
                a.setdefault('metadata_corrections',[]).append({'old_checked_at':a['checked_at'],
                    'new_checked_at':r['executed_at'],'reason':'Timestamp of persisted actual raw capture'})
                a['checked_at']=r['executed_at']
            if r.get('results'):
                a['search_result_urls']=[x['url'] for x in r['results']]
                a['search_result_mapping']=r.get('search_result_mapping','PER_QUERY')
        accepted,rejected=extract_evidence(task,r,now=now)
        session['plan'],changes=backfill(session['plan'],accepted,now=now)
        session.setdefault('extraction_amendments',[]).append({'task_id':task['task_id'],
            'checked_at':stamp(),'reason':'Corrected capture metadata / extraction; no new query claimed',
            'accepted_ids':[e['evidence_id'] for e in accepted],'rejected':rejected,'changes':len(changes)})
    refresh(session,now=now)
    return session

def run_round(session,chain,extractor,*,now=None):
    responses=[]
    for task in issue(session):
        response=chain.execute(task,max_sources=task['max_sources'])
        response.update(executed=True,executed_at=stamp())
        response['claims']=extractor(task,response)
        responses.append(response)
    if responses: consume(session,responses,now=now)
    return session

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['init','next','consume','export'])
    p.add_argument('--session',required=True); p.add_argument('--input'); p.add_argument('--output'); p.add_argument('--now')
    a=p.parse_args(); path=Path(a.session)
    if a.action=='init': s=start(json.loads(Path(a.input).read_text(encoding='utf-8')),now=a.now); result={'gaps':s['gaps'],'total_gaps':len(s['gaps']),'blocking_gaps':sum(g['criticality']=='BLOCKING' for g in s['gaps'])}
    else:
        s=json.loads(path.read_text(encoding='utf-8'))
        if a.action=='next': result={'tasks':issue(s),'round':s['round']+1,'completion':s['completion'],'limits':s['limits']}
        elif a.action=='consume': consume(s,json.loads(Path(a.input).read_text(encoding='utf-8')),now=a.now); result={'coverage':s['plan']['research_coverage'],'routes':s['plan']['route_closure'],'rejected':s['rejected_claims']}
        else:
            s['plan']['research_completion']=s['completion']; result=s['plan']
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output: Path(a.output).write_text(text,encoding='utf-8')
    else: print(text)

if __name__=='__main__': main()
