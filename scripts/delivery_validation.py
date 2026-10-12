"""Delivery boundary checks. Unknown booking facts are not invented or relaxed."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from travel_utils import trip_readiness

WEEKDAYS=('星期一','星期二','星期三','星期四','星期五','星期六','星期日')
ENGLISH=('monday','tuesday','wednesday','thursday','friday','saturday','sunday')
DATE_WEEKDAY=re.compile(r'(\d{4}-\d{2}-\d{2})\s*[（(·,，]?\s*((?:星期|周)[一二三四五六日天]|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',re.I)
META={'total','per_person','budget_gap','gap','currency','scope','basis','assumption','confidence','status','cost_type','not_exact_quote'}

def weekday(value):return WEEKDAYS[date.fromisoformat(value).weekday()]

def _money(value):
    if isinstance(value,bool):raise ValueError('Boolean is not a cost')
    try:v=Decimal(str(value))
    except (InvalidOperation,TypeError):raise ValueError('Numeric amount required')
    if not v.is_finite() or v<0:raise ValueError('Finite nonnegative amount required')
    return v

def _rounded(value):return value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def event_confirmed(event):
    """Check the explicit date evidence contract, never extrapolate a calendar rule."""
    try:target=date.fromisoformat(event.get('date',''))
    except (ValueError,TypeError):return False
    e=event.get('date_evidence') or {}
    excerpt=str(e.get('excerpt') or '')
    try:datetime.fromisoformat(str(e.get('checked_at','')).replace('Z','+00:00'))
    except ValueError:return False
    date_supported=target.isoformat() in excerpt or bool(re.search(fr'{target.year}[年/.-]\s*0?{target.month}[月/.-]\s*0?{target.day}(?:日|\b)',excerpt))
    return bool(event.get('status')=='OFFICIALLY_ANNOUNCED' and
        event.get('official_source_url') and e.get('source_url')==event['official_source_url'] and
        e.get('source_type')=='official' and e.get('checked_at') and
        e.get('applicable_year')==target.year and e.get('value')==target.isoformat() and
        date_supported)

def normalize_delivery_input(data):
    """Map existing schemas and derive calendar facts only; never invent budget scope."""
    if not isinstance(data,dict):raise ValueError('PLAN_DATA_INCOMPLETE: input must be a JSON object')
    out=deepcopy(data)
    for key in ('days','attractions','restaurant_candidates','hotel_candidates','place_registry','cost_ledger','public_sources','evidence'):
        if key not in out:continue
        if out[key] is None:out[key]=[]
        if not isinstance(out[key],list) or any(not isinstance(x,dict) for x in out[key]):
            raise ValueError('PLAN_DATA_INCOMPLETE: '+key+' must be a list of objects')
    for day in out.get('days',[]):
        for key in ('execution_nodes','itinerary_nodes','activities'):
            if key in day and (not isinstance(day[key],list) or any(not isinstance(x,dict) for x in day[key])):
                raise ValueError('PLAN_DATA_INCOMPLETE: days.'+key+' must be a list of objects')
    for key in ('savings','risks','checklist','bookings','key_decisions','food_recommendations'):
        if out.get(key) is None:out[key]=[]
        elif isinstance(out[key],(dict,str)):out[key]=[out[key]]
    p=out.get('trip_profile') or out.get('profile') or out.get('critical_info') or {}
    if not p:
        from state_consistency import FACTS
        p={k:out[k] for k in (*FACTS,'travel_window','duration_days') if k in out}
    out['trip_profile']=deepcopy(p);p=out['trip_profile']
    if not isinstance(p,dict):raise ValueError('PLAN_DATA_INCOMPLETE: trip_profile must be an object')
    if 'field_provenance' not in out and isinstance(p.get('field_provenance'),dict):out['field_provenance']=deepcopy(p['field_provenance'])
    for k in ('destination','start_date','end_date','duration_days','traveler_count','origin','budget_amount','budget_currency','budget_scope','airfare_included'):
        if k not in p and k in out:p[k]=out[k]
    aliases={'duration_days':('duration',),'traveler_count':('party_size',),'origin':('departure_city','departure_location'),
             'budget_amount':('target_budget','budget_total'),'budget_currency':('currency',),'budget_scope':('budget_basis',),
             'travel_window':('travel_dates','month')}
    for key,names in aliases.items():
        if key not in p:
            value=next((mapping[n] for mapping in (p,out) for n in names if n in mapping),None)
            if value is not None:p[key]=value
    supplied_scope=p.get('budget_scope');scope=str(supplied_scope or '').casefold()
    if any(x in scope for x in ('per_person','per person','每人','人均')):p['budget_scope']='PER_PERSON'
    elif any(x in scope for x in ('per_party','per party','whole party','whole trip','total','总预算','总额','两人合计','全团','全程')):p['budget_scope']='PER_PARTY'
    if 'airfare_included' not in p:
        if any(x in scope for x in ('不含机票','机票另计','flight excluded','airfare excluded','excluding airfare','not including flights')):p['airfare_included']=False
        elif any(x in scope for x in ('含机票','含往返机票','包含机票','including airfare','airfare included','flight included')):p['airfare_included']=True
    if supplied_scope!=p.get('budget_scope'):
        for mapping in (out,out.get('profile'),out.get('critical_info')):
            if isinstance(mapping,dict) and mapping.get('budget_scope')==supplied_scope:mapping['budget_scope']=p['budget_scope']
    if p.get('destination') and 'destination' not in out:out['destination']=p['destination']
    try:
        start,end=date.fromisoformat(p['start_date']),date.fromisoformat(p['end_date'])
        if end>=start:
            p.setdefault('duration_days',(end-start).days+1)
            p.setdefault('travel_window',start.isoformat()+' 至 '+end.isoformat())
    except (KeyError,ValueError,TypeError):pass
    from trip_entities import prepare_entities
    if p.get('intercity_mode')=='TRAIN' and 'intercity_fare_included' not in p:
        wording=str(out.get('subtitle',''))+' '+str(out.get('budget',{}).get('note',''))
        if re.search(r'不含.{0,8}(?:高铁|铁路|火车)',wording):p['intercity_fare_included']=False
        elif re.search(r'含.{0,8}(?:高铁|铁路|大交通|往返交通)',wording):p['intercity_fare_included']=True
    for field,idkey in (('restaurant_candidates','restaurant_id'),('attractions','attraction_id')):
        for row in out.get(field,[]):
            if isinstance(row,dict) and row.get(idkey):row.setdefault('id',row[idkey])
    for row in out.get('attractions',[]):
        for dest,src in (('ticket_price','ticket'),('opening_hours','open_hours'),('source_checked_at','checked_at')):
            if row.get(src) and not row.get(dest):row[dest]=row[src]
    return prepare_entities(out)

def validate_delivery_data(data):
    """Return correctable errors, warnings and a canonical scenario calculation."""
    from trip_entities import entity_errors
    from handbook_validation import validate_boundaries,cost_coverage
    boundaries=validate_boundaries(data);coverage=cost_coverage(data)
    errors=entity_errors(data)+boundaries['errors']+coverage['errors'];warnings=list(boundaries['warnings']);math={}
    if coverage['unknown_required_edges']:warnings.append({'code':'REQUIRED_COST_UNKNOWN','field':'required_cost_coverage','reason':'必需移动成本仍有未知项；预算合计仅为额度，不是完整真实成本'})
    def error(code,path,reason,repair):errors.append({'code':code,'field':path,'reason':reason,'repair':repair})
    p=data.get('trip_profile') or {};state=trip_readiness(data)
    for k in state['missing_critical_fields']:
        error('USER_INPUT_REQUIRED','trip_profile.'+k,'Critical user fact is missing or ambiguous','补充用户事实；预算必须包含人数口径和机票包含/排除，不可自行猜测')
    if not isinstance(data.get('days'),list) or not data.get('days'):
        error('PLAN_DATA_INCOMPLETE','days','A handbook needs daily planning content','提供按旅行窗口排列的每日安排')
    for i,d in enumerate(data.get('days',[])):
        if not isinstance(d,dict):error('PLAN_DATA_INCOMPLETE',f'days[{i}]','Day must be an object','改为每日结构对象');continue
        activities=d.get('activities') or d.get('itinerary_nodes') or (d.get('execution_graph') or {}).get('nodes')
        if not activities:
            error('PLAN_DATA_INCOMPLETE',f'days[{i}]','Missing daily content','提供活动或明确的抵达/返程缓冲安排')
        try:
            correct=weekday(d['date'])
            supplied=d.get('weekday')
            if supplied and str(supplied).casefold() not in {correct,correct.replace('星期','周'),'周天' if correct=='星期日' else correct,ENGLISH[date.fromisoformat(d['date']).weekday()]}:
                error('WEEKDAY_MISMATCH',f'days[{i}].weekday','Weekday contradicts ISO date',correct)
        except (KeyError,ValueError,TypeError):
            # Relative dates remain supported for an explicitly known date window.
            if p.get('start_date') or p.get('end_date'):
                error('INVALID_DAY_DATE',f'days[{i}].date','Expected a valid ISO day date','使用旅行窗口内的 YYYY-MM-DD')
    def check_text(value,path):
        if isinstance(value,str):
            for match in DATE_WEEKDAY.finditer(value):
                try:
                    dt=date.fromisoformat(match[1]);label=match[2].casefold()
                    valid={WEEKDAYS[dt.weekday()],WEEKDAYS[dt.weekday()].replace('星期','周'),ENGLISH[dt.weekday()]}
                    if dt.weekday()==6:valid.update({'星期天','周天'})
                    if label not in valid:error('WEEKDAY_MISMATCH',path,'Date and written weekday disagree',match[1]+' '+WEEKDAYS[dt.weekday()])
                except ValueError:error('INVALID_DATE',path,'Invalid written ISO date','修正日期')
        elif isinstance(value,dict):
            for k,v in value.items():
                if k not in {'raw_response','tool_response','initial_plan','revision_ledger','state_sync_ledger'}:check_text(v,path+'.'+k)
        elif isinstance(value,list):
            for i,v in enumerate(value):check_text(v,f'{path}[{i}]')
    check_text(data,'plan')
    events=data.get('seasonal_events') or []
    event_map={str(e.get('id') or e.get('name')):e for e in events if isinstance(e,dict)}
    for i,e in enumerate(events):
        if not isinstance(e,dict):continue
        if not event_confirmed(e):warnings.append({'code':'EVENT_UNVERIFIED','field':f'seasonal_events[{i}]','reason':'Only an unconfirmed candidate; historical patterns do not establish the target-year date'})
    for i,d in enumerate(data.get('days',[])):
        if not isinstance(d,dict):continue
        for collection in (d.get('activities',[]),d.get('itinerary_nodes',[]),(d.get('execution_graph') or {}).get('nodes',[])):
            for j,a in enumerate(collection):
                if not isinstance(a,dict):continue
                name=str(a.get('activity') or a.get('place') or a.get('name') or '')
                event=event_map.get(str(a.get('event_id'))) or next((e for e in event_map.values() if e.get('name') and str(e['name']) in name),None)
                if event is None and (a.get('event') or a.get('fixed_event') or a.get('event_date')):event=a
                if event is None:continue
                if not event_confirmed(event):error('EVENT_YEAR_EVIDENCE_MISSING',f'days[{i}].activities[{j}]','Fixed event has no applicable official year evidence','移出每日确定安排，放入未确认活动候选并提供普通活动替代')
                event_date=event.get('date') or event.get('event_date')
                if event_date and p.get('start_date') and p.get('end_date') and not p['start_date']<=event_date<=p['end_date']:
                    error('EVENT_DATE_OUTSIDE_WINDOW',f'days[{i}].activities[{j}]','Event date is outside the trip','移出每日项目；不得自行修改用户旅行日期')
                elif event_date and d.get('date')!=event_date:
                    error('EVENT_DAY_MISMATCH',f'days[{i}].activities[{j}]','Event scheduled on a different day','移动到已核实且在窗口内的活动日期')
    raw=data.get('budget') or {}
    if not isinstance(raw,dict):
        error('PLAN_DATA_INCOMPLETE','budget','Budget must be an object','使用结构化预算对象');raw={}
    count=p.get('traveler_count') or raw.get('traveler_count')
    if raw.get('traveler_count') and count!=raw['traveler_count']:error('BUDGET_COUNT_MISMATCH','budget.traveler_count','Budget party count differs','统一到 trip_profile.traveler_count')
    if raw.get('currency') and p.get('budget_currency') and raw['currency']!=p['budget_currency']:error('BUDGET_CURRENCY_MISMATCH','budget.currency','Scenario currency differs from profile','提供有来源的换汇或使用预算币种')
    scenarios=raw.get('scenarios') if isinstance(raw.get('scenarios'),dict) else {k:raw[k] for k in ('low','recommended','comfortable') if isinstance(raw.get(k),dict)}
    for key,spec in scenarios.items():
        if not isinstance(spec,dict):error('INVALID_BUDGET','budget.scenarios.'+key,'Expected category object','使用各费用类别金额');continue
        try:
            components={k:_money(v) for k,v in spec.items() if k not in META}
            if not components:raise ValueError('Cost components required; total alone is not a source')
            if not isinstance(count,int) or isinstance(count,bool) or count<1:raise ValueError('Positive integer party size required')
            total=_rounded(sum(components.values(),Decimal(0)));per=_rounded(total/count)
            cap=_money(p['budget_amount'])*(count if p.get('budget_scope')=='PER_PERSON' or str(p.get('budget_scope','')).lower().startswith('per person') else 1)
            gap=_rounded(max(Decimal(0),total-cap))
            expected={'total':total,'per_person':per,'budget_gap':gap,'gap':gap}
            for field in expected:
                if field in spec and _rounded(_money(spec[field]))!=expected[field]:
                    error('BUDGET_ARITHMETIC_MISMATCH',f'budget.scenarios.{key}.{field}','Value does not match canonical category calculation',float(expected[field]))
            if raw.get('scenarios') and key in raw and raw[key]!=spec:error('BUDGET_DUPLICATE_MISMATCH','budget.'+key,'Two scenario data sources disagree','只保留 budget.scenarios 中的一份分项源数据')
            math[key]={'components':{k:float(v) for k,v in components.items()},'total':float(total),'per_person':float(per),'budget_gap':float(gap),'currency':raw.get('currency') or p.get('budget_currency'),'scope':'PER_PARTY','cost_type':'PLANNING_ASSUMPTION','not_exact_quote':True}
        except (ValueError,KeyError,TypeError) as exc:error('INVALID_BUDGET','budget.scenarios.'+key,str(exc),'修正分项、预算口径和人数；不可补造报价')
    # Calendar-derived output fields cannot be supplied by the model.
    if math.get('recommended'):
        from cost_ledger import party_amount
        allocated={}
        for row in data.get('cost_ledger',[]):
            if not str(row.get('id','')).startswith('merchant-'):continue
            category={'hotel':'accommodation','food':'food'}.get(row.get('category'))
            if not category:continue
            try:
                if row.get('currency')!=p.get('budget_currency'):raise ValueError('Merchant currency requires explicit conversion')
                allocated[category]=allocated.get(category,Decimal(0))+party_amount(row,count)
            except (ValueError,TypeError):error('MERCHANT_COST_INVALID','cost_ledger.'+str(row.get('id')),'Merchant cost units or currency invalid','明确人数、房间、晚数与币种，再重新计算')
        for category,amount in allocated.items():
            if amount>Decimal(str(math['recommended']['components'].get(category,0))):
                error('MERCHANT_BUDGET_CONFLICT','budget.recommended.'+category,'Selected merchant allowances exceed this scenario allocation','增加对应分项或重新筛选商户；不可另写较小合计')
    for c in data.get('hotel_candidates',[])+data.get('restaurant_candidates',[]):
        if c.get('selected') is True and not c.get('planning_cost'):
            warnings.append({'code':'MERCHANT_COST_UNVERIFIED','field':str(c.get('id')),'reason':'Selected merchant has no declared cost; booking remains unverified'})
    if data.get('budget_math') is not None and data['budget_math']!=math:
        error('BUDGET_DERIVED_DATA_MISMATCH','budget_math','Derived budget values disagree with source categories','从 budget.scenarios 的分项重新计算，不保留独立手填合计')
    closure=data.get('budget_reconciliation') or {}
    if closure and data.get('cost_ledger') and data.get('execution_evaluation',{}).get('evaluated_at'):
        from cost_ledger import reconcile_budget
        quotes={r['quote_id']:r for name in ('hotel_availability','flight_availability') for r in data.get(name,[]) if r.get('quote_id')}
        expected=reconcile_budget(p,data['cost_ledger'],quotes,data.get('exchange_rates'),now=data['execution_evaluation']['evaluated_at'])
        for k in ('party_total','per_person_total','verified_cost_party','estimated_cost_party','budget_gap_per_person','known_subtotal_party'):
            if closure.get(k)!=expected[k]:error('COST_DERIVED_DATA_MISMATCH','budget_reconciliation.'+k,'Cost result differs from the canonical ledger',expected[k])
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'warnings':warnings,'budget_math':math}

def apply_delivery_checks(data):
    try:out=normalize_delivery_input(data);check=validate_delivery_data(out)
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        out=deepcopy(data) if isinstance(data,dict) else {}
        out['delivery_validation']={'status':'FAIL','errors':[{'code':'PLAN_DATA_INCOMPLETE','field':'input_schema','reason':str(exc),'repair':'按 delivery-input/practical-delivery 字段类型修正；未知值保持 null，不粘贴对象字符串'}],'warnings':[],'budget_math':{}}
        return out
    out['delivery_validation']=check
    if check['status']=='PASS':
        for day in out.get('days',[]):
            try:day['weekday']=weekday(day['date'])
            except (KeyError,ValueError,TypeError):pass
        if check['budget_math']:out['budget_math']=check['budget_math']
    return out

def planning_delivery_gate(plan):
    check=validate_delivery_data(plan);errors=list(check['errors'])
    errors.extend({'code':x.get('code','PLAN_CONFLICT'),'field':x.get('field','plan_qa'),'reason':x.get('reason','Known itinerary conflict'),'repair':'修正已知冲突后重新运行标准入口'} for x in plan.get('plan_qa',{}).get('findings',[]))
    if plan.get('route_closure',{}).get('route_structure_status')=='INCOMPLETE':
        errors.append({'code':'PLAN_DATA_INCOMPLETE','field':'execution_graph','reason':'Malformed route structure; missing facts alone are allowed','repair':'修正节点/边覆盖关系；未知时间与费用保持 unavailable'})
    if plan.get('budget_reconciliation',{}).get('issues'):
        errors.append({'code':'COST_LEDGER_INVALID','field':'cost_ledger','reason':'Invalid cost records','repair':'修正金额、范围、来源和数量；无报价的项保留 UNAVAILABLE'})
    quotes_missing=any(v.get('status') not in {'VERIFIED','NOT_APPLICABLE'} for v in plan.get('quote_validation',{}).values())
    booking=plan.get('readiness',{}).get('booking_readiness','NOT_READY')
    result={'status':'BLOCKED' if errors else 'READY' if booking=='READY' else 'PROVISIONAL',
            'can_generate':not errors,'data_state':'PLAN_DATA_INCOMPLETE' if any(e['code'] in {'USER_INPUT_REQUIRED','PLAN_DATA_INCOMPLETE','INVALID_DAY_DATE'} for e in errors) else 'CONFLICT' if errors else 'QUOTE_NOT_OBTAINED' if quotes_missing else 'INFORMATION_UNVERIFIED' if booking!='READY' else 'VERIFIED',
            'booking_readiness':booking,'errors':errors,'warnings':check['warnings'],
            'budget_verified':booking=='READY' and plan.get('budget_reconciliation',{}).get('closure_status')=='PASS' and not plan.get('budget_reconciliation',{}).get('estimated_cost_party')}
    return result
