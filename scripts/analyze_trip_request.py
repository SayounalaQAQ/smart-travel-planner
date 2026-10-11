#!/usr/bin/env python3
"""Local, conservative preflight for user trip requests; never creates an itinerary."""
import argparse
import json
import re
from travel_utils import classify_profile_fields, decision_mode, discovery_workflow, detect_hidden_constraints, trip_readiness, ask_value_test


DESTINATIONS=(
    (r'东京|東京|tokyo','Tokyo','city'),(r'京都|kyoto','Kyoto','city'),
    (r'大阪|osaka','Osaka','city'),(r'北海道|hokkaido','Hokkaido','region'),
    (r'日本|japan','Japan','country'),(r'韩国|南韩|south korea|korea','South Korea','country'),
    (r'欧洲|europe','Europe','continent'),
)


def analyze_request(text):
    source=text.strip(); profile={}; provenance={}
    # Preserve explicit base-city intent when a secondary day-trip city appears
    # later in the sentence (e.g. Osaka base, Kyoto day trip).
    base_match=re.search(r'(东京|東京|大阪|京都|首尔|釜山)\s*(?:为基地|作基地|做基地|为据点|作据点|做据点|作为住宿基地)',source,re.I)
    base_aliases={'东京':'Tokyo','東京':'Tokyo','大阪':'Osaka','京都':'Kyoto','首尔':'Seoul','釜山':'Busan'}
    if base_match:
        profile.update(destination=base_aliases[base_match.group(1)],destination_scope='city')
        provenance['destination']='user'
        day_trips=re.findall(r'(东京|東京|大阪|京都|首尔|釜山)\s*(?:一日往返|当天往返|日归|day\s*trip)',source,re.I)
        if day_trips:
            profile['day_trip_destinations']=[base_aliases.get(city,base_aliases.get(city.title())) for city in day_trips]
            provenance['day_trip_destinations']='user'
    for pattern,name,scope in DESTINATIONS:
        if profile.get('destination'):
            break
        if re.search(pattern,source,re.I):
            profile.update(destination=name,destination_scope=scope)
            provenance['destination']='user'
            break
    duration=re.search(r'(\d+|一|二|两|三|四|五|六|七|八|九|十)\s*(?:天|日|days?|weeks?|周|星期)',source,re.I)
    if duration:
        n={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(duration.group(1),int(duration.group(1)) if duration.group(1).isdigit() else 0)
        profile['duration_days']=n*7 if re.search(r'周|星期|weeks?',duration.group(0),re.I) else n; provenance['duration_days']='user'
    # Keep the 人 in 人民币 from being mistaken for the headcount suffix.
    count=re.search(r'(\d+|一|二|两|三|四|五|六|七|八|九|十)\s*(?:个人|人(?!民币)|位|travelers?|people)',source,re.I)
    if count:
        profile['traveler_count']=int(count.group(1)) if count.group(1).isdigit() else {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}[count.group(1)]; provenance['traveler_count']='user'
    elif re.search(r'(?:我)?和(?:女朋友|男朋友|妻子|丈夫|伴侣|对象|女友|男友)',source):
        profile['traveler_count']=2; provenance['traveler_count']='user'
    elif re.search(r'独自|一个人|solo',source,re.I):
        profile['traveler_count']=1; provenance['traveler_count']='user'
    amount=re.search(r'(?:预算|budget)\s*(?:(?:为|是|约|大约|[:：])\s*)?(?:(?:每人|人均)\s*)?[¥￥$€]?\s*([\d,]+(?:\.\d+)?)\s*(元|人民币|CNY|JPY|USD|EUR|日元|韩元)?',source,re.I)
    if amount:
        profile['budget_amount']=float(amount.group(1).replace(',','')); provenance['budget_amount']='user'
        cur=amount.group(2)
        if cur:
            profile['budget_currency']='CNY' if cur in {'元','人民币'} else {'日元':'JPY','韩元':'KRW'}.get(cur,cur.upper())
            provenance['budget_currency']='user'
    unit=None
    if re.search(r'每人|人均|一个人|per\s*(?:person|traveler)',source,re.I): unit='per person'
    elif re.search(r'两人总|全团|总预算|总额|全程预算|total\s+budget|per\s+party',source,re.I): unit='whole party'
    flight=None
    if re.search(r'不含(?:国际)?机票|不包括(?:国际)?机票|机票另计|excluding\s+(?:international\s+)?airfare|flight(?:s)?\s+excluded|not\s+including\s+flight',source,re.I): flight='excluding airfare'
    elif re.search(r'含(?:往返|国际)?机票|包含(?:往返|国际)?机票|including\s+airfare|flight(?:s)?\s+included',source,re.I): flight='including airfare'
    if unit and flight:
        profile['budget_scope']=f'{unit}, {flight}'; provenance['budget_scope']='user'
    month=re.search(r'(?:20\d{2}\s*年\s*)?(\d{1,2})\s*月',source)
    if month:
        year=re.search(r'(20\d{2})\s*年',source)
        profile['travel_window']=f'{year.group(1) if year else "year unspecified"}-{int(month.group(1)):02d}'; provenance['travel_window']='user'
    date_range=re.search(r'(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*(?:至|到|—|–|-|~|～)\s*20?\d{2}[-/.年]?\d{1,2}[-/.月]\d{1,2}日?)',source)
    if date_range:
        profile['travel_window']=date_range.group(1); provenance['travel_window']='user'
    departure=re.search(r'(?:从|自)\s*([^，。,.\s]{2,20})\s*出发|出发地\s*[:：是]?\s*([^，。,.\s]{2,20})|from\s+([A-Z][A-Za-z -]{1,30})',source,re.I)
    if departure:
        profile['origin']=next(v for v in departure.groups() if v); provenance['origin']='user'
    if not profile.get('origin'):
        short_origin=re.search(r'(上海|北京|广州|深圳|杭州|成都|香港)\s*出发',source)
        if short_origin: profile['origin']=short_origin.group(1); provenance['origin']='user'
    # 女朋友/男朋友 are travel companions, not hosts; avoid substring matching them as 朋友.
    free=bool(re.search(r'(?<!女)(?<!男)朋友|亲属|免费住宿|可以让我住|free\s+(?:stay|accommodation)|friend.{0,35}(?:host|stay|accommodation)',source,re.I))
    nights=re.search(r'(\d+)\s*晚',source)
    if free:
        profile['free_accommodation']=True; provenance['free_accommodation']='user'
        if nights: profile['free_nights']=int(nights.group(1)); provenance['free_nights']='user'
        loc=re.search(r'(?:住在|住我|朋友在|朋友住(?:在)?|位于)\s*([^，。,\.\s]{2,20})',source)
        if loc: profile['accommodation_location']=loc.group(1); provenance['accommodation_location']='user'
        stay_dates=re.search(r'(\d{1,2}\s*月\s*\d{1,2}\s*(?:日|号)?\s*(?:至|到|[-~～])\s*\d{1,2}\s*月\s*\d{1,2}\s*(?:日|号)?)',source)
        if stay_dates: profile['free_stay_dates']=stay_dates.group(1); provenance['free_stay_dates']='user'
    if re.search(r'不喜欢早起|不想早起|不要早起|晚点出门|sleep in',source,re.I):
        profile['sleep_schedule']='late_start'; provenance['sleep_schedule']='user'
    if re.search(r'不要太累|不想太累|轻松一点|别太累|relaxed|not too tiring',source,re.I):
        profile['pace']='relaxed'; provenance['pace']='user'
    step=re.search(r'(?:最多|不超过|控制在|no more than)\s*(?:走|walk)?\s*(\d[\d,]*|一万(?:二|两|三|四|五|六|七|八|九)?|两万|三万)\s*(?:步|steps)',source,re.I)
    if step:
        raw=step.group(1).replace(',','')
        if raw.isdigit(): count_steps=int(raw)
        elif raw=='一万': count_steps=10000
        elif raw.startswith('一万'): count_steps=10000+{'二':2000,'两':2000,'三':3000,'四':4000,'五':5000,'六':6000,'七':7000,'八':8000,'九':9000}[raw[-1]]
        else: count_steps={'两万':20000,'三万':30000}[raw]
        profile['walking_tolerance_steps']=count_steps; provenance['walking_tolerance_steps']='user'
    interests=[]
    for pattern,tag in ((r'动漫|anime','anime'),(r'购物|shopping','shopping'),(r'美食|吃|food','food'),(r'自然|nature','nature'),(r'历史|history','history'),(r'摄影|拍照|photograph','photography')):
        if tag=='shopping' and re.search(r'不(?:想|要|考虑).*购物|购物(?:另计|除外|不考虑)',source):
            continue
        if re.search(pattern,source,re.I): interests.append(tag)
    if re.search(r'二次元|手办|圣地巡礼|复古游戏',source) and 'anime' not in interests:interests.append('anime')
    if interests: profile['interests']=interests; provenance['interests']='user'
    from experience_discovery import discover_experiences, research_intents
    experience=discover_experiences(source,profile)
    if experience['experience_preferences']:
        profile['experience_preferences']=experience['experience_preferences']
        provenance['experience_preferences']='user intent; priority/details not yet clarified'
    cash_question=next((q for q in experience['questions'] if q['field']=='budget_purpose'),None)
    if cash_question:
        profile['available_funds_amount']=cash_question['available_funds_amount']
        provenance['available_funds_amount']='user; currency and travel allocation not confirmed'
    area_match=re.search(r'(心斋桥|難波|难波|本町|天王寺|梅田)',source)
    if area_match:
        area_alias={'難波':'难波'}
        profile['lodging_area']=area_alias.get(area_match.group(1),area_match.group(1)); provenance['lodging_area']='user'
    auto_mode=decision_mode(source)
    profile.update({
        'lodging_candidates':[], 'lodging_recommendation':None, 'lodging_selection_status':'DISCOVERING',
        'airport_candidates':[], 'flight_candidates':[], 'flight_recommendation':None,'flight_selection_status':'DISCOVERING',
        'attraction_candidates':[], 'attraction_recommendations':[], 'attraction_selection_status':'DISCOVERING',
        'transit_candidates':[], 'transit_recommendation':None,'transit_selection_status':'DISCOVERING',
        'restaurant_candidates':[], 'restaurant_recommendations':[],'restaurant_selection_status':'DISCOVERING',
        'decision_status':'DISCOVERING'
    })
    # The suspicious sequence is surfaced for re-planning, never accepted as a verified route.
    route_order=[(token,label) for token,label in (('浅草','Asakusa'),('迪士尼','Disney'),('秋叶原','Akihabara'),('台场','Odaiba')) if token in source]
    route_order.sort(key=lambda pair:source.find(pair[0]))
    route_review=None
    if len(route_order)>=3:
        route_review={'status':'ROUTE_FEASIBILITY_REVIEW','requested_chain':[label for _,label in route_order],
                      'reason':'该请求把多个分散区域压进同一天；需先核验门到门交通、入园时间与停留时长，再按区域拆分。当前没有声称具体分钟数。',
                      'proposal':'迪士尼单独安排完整一天；浅草与秋叶原按东侧路线同日聚类；台场另安排湾岸时段。'}
    data={'trip_profile':profile,'field_provenance':provenance}
    state=trip_readiness(data)
    constraints=detect_hidden_constraints(data)
    questions=[]; seen=set()
    for item in constraints:
        if auto_mode and item.get('field') in {'pace','interests'}:continue
        if item.get('field')=='budget_scope' and any(q['field']=='budget_purpose' for q in experience['questions']):continue
        # A broad destination is a research-then-choice item, never a blind
        # demand that the user name a city before the agent compares options.
        if item.get('field')=='destination_choice' and item.get('decision_status')=='DISCOVERING': continue
        if item['impact'] not in {'HIGH','MEDIUM'} or item['question'] in seen or not ask_value_test(item): continue
        questions.append(item); seen.add(item['question'])
        if len(questions)>=5: break
    # Combine critical facts, while reserving room for a meaningful interest ask.
    extra=experience['questions']
    if extra:
        critical=[q for q in extra if q['priority']=='P0']
        subjective=[q for q in extra if q['priority']=='P2'][:3]
        questions=(critical+questions[:max(0,5-len(critical)-min(2,len(subjective)))]+subjective)[:5]
    workflow=discovery_workflow(profile,auto_decision=auto_mode,required_missing=state['missing_critical_fields'])
    workflow['research_queue']=[{**item,'status':'DISCOVERING'} for item in workflow['research_queue']]
    state_machine=['REQUEST_RECEIVED','RESEARCHING']
    if not state['ready_for_provisional_plan']: state_machine.append('USER_REQUIRED_INFO_PENDING')
    state_machine.append('PROVISIONAL_PLAN')
    state_machine.append('AUTO_SELECTED' if auto_mode else 'USER_DECISION_REQUIRED')
    if not auto_mode: state_machine.append('USER_CONFIRMED')
    state_machine.extend(['FINAL_OPTIMIZATION','FINAL_PLAN','DOCX'])
    return {'mode':state['mode'],'readiness':state['readiness'],'score_note':state['score_note'],
            'trip_profile':profile,'field_provenance':provenance,
            'information_classification':classify_profile_fields(profile),
            'state_machine':state_machine,'planning_level':'LEVEL_1_PROVISIONAL' if set(state['missing_critical_fields']).issubset({'destination_choice'}) else ('LEVEL_1_PROVISIONAL' if state['ready_for_formal_plan'] else 'RESEARCH_ONLY'),
            'decision_mode':'AUTO_DECISION_MODE' if auto_mode else 'USER_CHOICE_MODE',
            'agent_discovery':workflow,
            'missing_critical_fields':state['missing_critical_fields'],'route_state':state['route_state'],
            'hidden_constraints':constraints,'questions':questions,'questions_stage':'AFTER_FIRST_PASS_RESEARCH',
            'experience_discovery':experience,'experience_research_intents':research_intents(profile),
            'research_first':True,'provisional_plan_allowed':state['ready_for_provisional_plan'],
            'formal_plan_allowed':state['ready_for_formal_plan'],
            'route_review':route_review,
            'research_targets':['目的地候选与区域差异','出行季节/日期敏感信息','机场与航班候选','住宿区域及酒店候选/价格口径','景点与免费资源候选','交通/票券/换乘方案','餐厅候选','节假日与主要风险']}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--text',required=True); parser.add_argument('--output')
    args=parser.parse_args(); result=analyze_request(args.text); rendered=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(rendered,encoding='utf-8')
    print(rendered)


if __name__=='__main__': main()
