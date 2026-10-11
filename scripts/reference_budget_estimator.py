"""Separate sourced planning references from booking costs and cap allocations."""
from collections import defaultdict
import math
from data_freshness import freshness

def reference_ledger(plan,*,now=None):
    result=[]
    for e in plan.get('research_evidence',[]):
        if e['claim_type']!='cost_reference':continue
        v=e['value']
        ttl={'hotel':'hotel_quote','flight':'flight_quote','transit':'route','airport_transfer':'route'}.get(v['category'],'attraction_static')
        if freshness(e,ttl,now=now)['refresh_required']:continue
        result.append({'reference_id':e['evidence_id'],**v,'subject':e['subject'],'limitations':e.get('limitations',[]),'source':e['source_url'],'checked_at':e['retrieved_at'],
            'applicability':e['applicable_date'],'evidence_ids':[e['evidence_id']],
            'estimate_type':'CURRENT_PRICE_REFERENCE','not_exact_quote':True})
    return result

def scenario_estimate(spec,refs,required,count):
    """Host-declared billable quantities remain assumptions, not booking facts.

    quantity_party is the total number of priced units for the whole party.
    No implicit nights/meals/rides or currency conversion is introduced here.
    """
    lookup={r['reference_id']:r for r in refs};lines=[];covered=set();errors=[]
    if not isinstance(spec,dict):return {'status':'NOT_ENOUGH_EVIDENCE','total':None}
    for line in spec.get('lines',[]):
        ref=lookup.get(line.get('reference_id'));quantity=line.get('quantity_party')
        if not ref or not isinstance(quantity,(int,float)) or isinstance(quantity,bool) or not math.isfinite(quantity) or quantity<=0 or not line.get('quantity_basis') or line.get('coverage')!='FULL_TRIP_CATEGORY':
            errors.append('Missing fresh reference or explicit full-category billable quantity/basis');continue
        covered.add(ref['category']);lines.append({'reference_id':ref['reference_id'],'category':ref['category'],
            'scope':ref['scope'],'quantity_party':quantity,'quantity_basis':line['quantity_basis'],
            'unit_price':ref['amount'],'currency':ref['currency'],'party_amount':ref['amount']*quantity,
            'source':ref['source'],'applicability':ref['applicability'],'limitations':ref['limitations']})
    missing=sorted(set(required)-covered);currencies={r['currency'] for r in lines}
    if missing or errors or len(currencies)!=1 or not count:
        return {'status':'NOT_ENOUGH_EVIDENCE','total':None,'missing_categories':missing,'issues':errors+(['No single supported currency'] if len(currencies)!=1 else [])}
    total=round(sum(r['party_amount'] for r in lines),2)
    return {'status':'EVIDENCE_BACKED_PLANNING_ESTIMATE','total':total,'scope':'PER_PARTY',
        'per_person':round(total/count,2),'currency':next(iter(currencies)),'lines':lines,
        'confidence':'estimated','not_exact_quote':True,
        'limitations':['Quantities and full-category coverage are explicit host planning assumptions; not independently verified consumption',
                       'Only listed expense categories; no implicit contingency, conversion or other-date quote promotion']}

def estimate_budget(plan,*,now=None):
    refs=reference_ledger(plan,now=now);groups=defaultdict(list)
    for row in refs:groups[(row['category'],row['currency'],row['scope'])].append(row)
    ranges=[]
    for (category,currency,scope),rows in groups.items():
        # These bounds compare published items; they are NOT an entire 8-day budget.
        ranges.append({'category':category,'estimate_type':'EVIDENCE_ITEM_RANGE','lower':min(r['amount'] for r in rows),
            'upper':max(r['amount'] for r in rows),'currency':currency,'scope':scope,
            'basis':[r['reference_id'] for r in rows],'confidence':'medium',
            'coverage':'Published items only; quantity, choices and unpriced items excluded'})
    required=['transit','attractions','food','airport_transfer','internet','insurance','hotel','flight']
    if plan.get('trip_profile',{}).get('intercity_mode') == 'TRAIN':
        required = sorted(set(plan['trip_profile'].get('budget_categories', ['transit','attractions','food','hotel','misc'])) - {'emergency'})
    covered={r['category'] for r in refs}
    specs=plan.get('reference_scenario_inputs',{})
    required_scenario=sorted(set(required)|{r['category'] for r in plan.get('budget_reconciliation',{}).get('rows',[]) if r.get('category') and r['category']!='emergency' and not r.get('optional')})
    scenarios={key:scenario_estimate(specs.get(key),refs,required_scenario,plan.get('trip_profile',{}).get('traveler_count')) for key in ('LOW_COST_SCENARIO','BALANCED_SCENARIO','COMFORT_SCENARIO')}
    balanced=scenarios['BALANCED_SCENARIO']
    return {'reference_ledger':refs,'ranges':ranges,'cost_reference_coverage':{'covered_categories':sorted(covered),
        'required_categories':required,'ratio':len(covered & set(required))/len(required) if required else 0},
        'planning_budget':'COMPLETE' if all(x['total'] is not None for x in scenarios.values()) else 'PARTIAL' if refs else 'UNVERIFIED','booking_cost':plan.get('budget_reconciliation',{}),
        'budget_allocation':plan.get('budget',{}).get('cap_allocation',{}),
        'scenarios':scenarios,
        'full_trip_estimate':balanced if balanced['total'] is not None else None,'note':'Reference ranges must not trigger a real budget conflict or become VERIFIED_QUOTE'}
