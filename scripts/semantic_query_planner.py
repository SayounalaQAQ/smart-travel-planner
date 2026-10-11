"""Resolve a research intent before generating one fact-specific, gated query."""
import re

PLACEHOLDER=re.compile(r'UNRESOLVED|UNAVAILABLE|待核|待定|待确认|实际出发机场|住宿区域|换乘锚点|附近.*餐饮|酒店附近晚餐|具体.*未知|^Hotel$|^Park$',re.I)
NEEDS={
 'opening_hours':('OPENING_HOURS','opening hours','営業時間'),
 'ticket_price':('ADMISSION_PRICE','admission ticket price','入場料金'),
 'reservation_required':('RESERVATION_RULE','reservation required','予約 必要'),
 'transport_info':('ACCESS','nearest station access entrance','最寄り駅 アクセス'),
 'address':('ADDRESS','address','住所'), 'nearest_station':('ACCESS','nearest station exit access','最寄り駅 出口 アクセス'),
 'check_in_out':('CHECK_IN_OUT','check in check out time','チェックイン チェックアウト 時間'),
 'room_categories':('ROOM_TYPES','double room types','ダブル 客室'), 'breakfast':('BREAKFAST','breakfast included','朝食'),
 'name':('ENTITY_DISCOVERY','restaurant near','レストラン 店舗'), 'cuisine':('CUISINE','menu food','メニュー'),
 'reservation':('RESERVATION_RULE','reservation policy','予約'), 'price_reference':('CURRENT_MENU_PRICE','menu prices','メニュー 値段'),
 'backup':('RESTAURANT_DISCOVERY','restaurant alternative','近く レストラン'),
 'airport_pairs':('AIRPORT_ROUTES','airline direct airport routes','航空会社 直行便 空港'),
 'duration_reference':('FLIGHT_DURATION','airline flight duration','航空会社 飛行時間'),
 'rate':('EXCHANGE_RATE','exchange rate current','現在 為替 レート'),
 'climate':('HISTORICAL_CLIMATE','April historical climate normals','4月 気候 平年値'),
 'entry':('ENTRY_RULE','visitor visa entry','外務省 短期滞在 査証'),
 'steps_basis':('WALKING_LOAD','walking distance station entrances','徒歩 距離 駅 入口')}
ALIASES={'黑门市场':'黒門市場','心斋桥站':'心斎橋駅','道顿堀戎桥':'道頓堀 戎橋','上海':'Shanghai',
         '伏见稻荷下段鸟居':'伏見稲荷大社','中之岛公园水岸':'中之島公園','大阪城公园':'大阪城公園'}

def clean_entity(value):
    value=re.sub(r'[（(][^）)]*[）)]','',str(value or ''))
    value=re.sub(r'\s+',' ',value).strip()
    return ALIASES.get(value,value)

def local_area(area):
    """Resolve a meal search to a destination district, never a travel-day chain."""
    for tokens, name in [(('伏见','伏見'),'Fushimi Inari Kyoto Japan'),
                         (('天王寺','阿倍野'),'Tennoji Osaka Japan'),
                         (('中之岛','中之島'),'Nakanoshima Osaka Japan'),
                         (('心斋桥','心斎橋','美国村'),'Shinsaibashi Osaka Japan'),
                         (('Minami','难波','道顿堀'),'Namba Osaka Japan')]:
        if any(t in str(area) for t in tokens):return name
    return ''

def build_intent(gaps,profile,plan=None,attempt=0):
    g=gaps[0]; target=g['target'];kind=target['kind'];field=g['required_field'];plan=plan or {}
    location=clean_entity(profile.get('research_location') or profile.get('destination',''))
    if any(token in location for token in ('大阪','Osaka')):location='Osaka Japan'
    elif '东京' in location:location='Tokyo Japan'
    country=profile.get('country') or 'Japan'
    japan=country in {'Japan','日本','JP'}
    lang=('ja' if attempt%2 else 'en') if japan else (profile.get('research_language','en') if not attempt%2 else 'en')
    entity=clean_entity(g['entity']); need,english,japanese=NEEDS.get(field,('ENTITY_DISCOVERY','official information','公式 情報'))
    if any(x in entity for x in ('伏见','伏見','Fushimi','京都','Kyoto','清水寺','东山','祇园')):location='Kyoto Japan'
    if kind=='cost' and target.get('category') in {'internet','insurance','visa_related'}:location=country
    exact=field=='exact_quote'
    if kind=='hotel':entity=clean_entity(profile.get('hotel') or entity)
    if kind=='flight' or kind=='flight_static' or g['category']=='FLIGHT_SCHEDULE':
        entity=clean_entity(profile.get('origin') or 'Shanghai')+' '+clean_entity(profile.get('destination') or 'Osaka')
        if '大阪' in entity:entity=clean_entity(profile.get('origin') or 'Shanghai')+' Osaka'
        location=country;need,english,japanese=NEEDS['duration_reference' if field!='airport_pairs' else field]
    if exact:
        need='EXACT_HOTEL_QUOTE' if kind=='hotel' else 'EXACT_FLIGHT_QUOTE'
        english='double room availability stay total' if kind=='hotel' else 'round trip flight fare baggage itinerary'
        japanese='ダブル 空室 宿泊総額' if kind=='hotel' else '往復 航空券 運賃 手荷物'
    origin=destination=None
    if kind=='route' and g['category']!='FLIGHT_SCHEDULE':
        origin=clean_entity(target.get('from'));destination=clean_entity(target.get('to'))
        for side in ('from','to'):
            node=next((n for d in plan.get('days',[]) for n in d.get('execution_graph',{}).get('nodes',[]) if n.get('place_id')==target.get(side+'_place_id')),None)
            if node:
                name=clean_entity(node.get('place')) if node.get('location_status')=='RESOLVED' else ''
                if name and node.get('role')=='MEAL' and node.get('address'):name+=' '+node['address']
                if side=='from':origin=name
                else:destination=name
        entity=origin+' to '+destination
        variant=attempt%2
        need='DIRECT_WALK' if variant==0 else 'PUBLIC_TRANSIT'
        english='walking route distance minutes' if variant==0 else 'metro stations fare transfer travel time'
        japanese='徒歩 ルート 距離 所要時間' if variant==0 else '地下鉄 駅 運賃 乗換 所要時間'
        if g['category']=='AIRPORT_TRANSFER' and any('机场' in str(x) for x in (origin,destination)):
            need='TERMINAL_ACCESS';english='terminal train station shuttle connection';japanese='ターミナル 駅 連絡 シャトル'
        endpoints=[next((n for d in plan.get('days',[]) for n in d.get('execution_graph',{}).get('nodes',[]) if n.get('place_id')==target.get(side+'_place_id')),{}) for side in ('from','to')]
        if profile.get('intercity_mode')=='TRAIN' and all(n.get('role')=='STATION' for n in endpoints):
            need='INTERCITY_RAIL';english='railway train timetable fare';japanese='鉄道 時刻表 運賃'
    if kind=='cost':
        category=target.get('category',g['entity'])
        entities=([r.get('name') for r in plan.get('restaurant_candidates',[]) if r.get('name') and r.get('address')]
                  if category=='food' else [n['place'] for d in plan.get('days',[]) for n in d.get('execution_graph',{}).get('nodes',[]) if n.get('role')=='ACTIVITY'] if category=='attractions' else [])
        if entities: entity=clean_entity(entities[attempt%len(entities)])
        else:
            entity=({'transit':'Osaka Metro','internet':'Japan tourist data SIM 8 days','insurance':'Japan visitor travel insurance 8 days',
                      'visa_related':'Japan visitor visa','misc':'Osaka luggage storage'} if japan else
                    {'transit':location+' 地铁 交通','internet':country+' 旅行上网','insurance':country+' 旅行保险',
                     'visa_related':country+' 签证','misc':location+' 行李寄存'}).get(category,'')
        need,english,japanese=NEEDS['price_reference' if category=='food' else 'ticket_price']
        if category in {'transit','internet','insurance','visa_related','misc'}:
            need='SERVICE_PRICE';english='price tariff';japanese='料金'
    if kind=='entry':entity=country;location=country
    if kind=='exchange':entity=profile.get('destination_currency','JPY' if japan else '')+' '+profile.get('budget_currency','CNY');location='currency market'
    if kind=='weather':
        entity=location;location=location or country
        month=str(profile.get('start_date') or '')[5:7]
        if month and month!='04':english=f'{month} historical climate normals';japanese=f'{int(month)}月 気候 平年値'
    if kind=='restaurant' and (PLACEHOLDER.search(str(g['entity'])) or PLACEHOLDER.search(entity) or not any(r.get('place_id')==target.get('place_id') and r.get('name') for r in plan.get('restaurant_candidates',[]))):
        entity=local_area(target.get('area'));need='RESTAURANT_DISCOVERY';english='restaurant menu prices address';japanese='レストラン メニュー 料金 住所'
        if not japan:
            area=clean_entity(target.get('area'))
            entity=(location+' '+area).strip() if area and not re.search(r'→|/|或',area) else ''
        if 'Kyoto' in entity:location='Kyoto Japan'
    if kind=='walking':
        day=next((d for d in plan.get('days',[]) if d.get('date')==g.get('travel_date')), {})
        places=[clean_entity(n.get('place')) for n in day.get('execution_graph',{}).get('nodes',[]) if n.get('role')=='ACTIVITY' and not PLACEHOLDER.search(str(n.get('place','')))]
        entity=' to '.join(places[:2]) if len(places)>1 else ''
        need='WALKING_LOAD';english='walking route distance entrances';japanese='徒歩 ルート 距離 入口'
    if kind=='conflict':
        code=target.get('conflict',{}).get('code','');entity=location
        need='SHORTER_ROUTE' if 'WALK' in code else 'CHEAPER_ALTERNATIVE' if 'BUDGET' in code else 'LATE_START_ALTERNATIVE'
        english={'SHORTER_ROUTE':'shorter walking route alternate entrance','CHEAPER_ALTERNATIVE':'economy hotel total transport cost',
                 'LATE_START_ALTERNATIVE':'late morning opening hours alternative'}[need]
        japanese={'SHORTER_ROUTE':'徒歩 短いルート 入口','CHEAPER_ALTERNATIVE':'格安 ホテル 交通費','LATE_START_ALTERNATIVE':'午後 観光 営業時間'}[need]
    chinese={'OPENING_HOURS':'营业时间','ADMISSION_PRICE':'门票价格','RESERVATION_RULE':'预约规则','ACCESS':'最近车站 出口 交通',
        'ADDRESS':'地址','CHECK_IN_OUT':'入住退房时间','ROOM_TYPES':'双人房房型','BREAKFAST':'早餐',
        'CUISINE':'菜单 餐饮类型','CURRENT_MENU_PRICE':'菜单价格','RESTAURANT_DISCOVERY':'餐厅 菜单价格 地址',
        'DIRECT_WALK':'步行路线 距离 用时','PUBLIC_TRANSIT':'地铁站 换乘 票价 用时','TERMINAL_ACCESS':'航站楼 接驳',
        'SERVICE_PRICE':'收费标准','EXACT_HOTEL_QUOTE':'双人房 库存 全程入住总价','EXACT_FLIGHT_QUOTE':'往返机票 行李 总价',
        'INTERCITY_RAIL':'铁路 车次 时刻 票价',
        'HISTORICAL_CLIMATE':str(profile.get('start_date',''))[5:7]+'月 历史气候',
        'ENTRY_RULE':'入境签证','EXCHANGE_RATE':'当前汇率','WALKING_LOAD':'步行路线 距离 入口',
        'SHORTER_ROUTE':'短途步行 替代入口','CHEAPER_ALTERNATIVE':'经济酒店 总交通成本','LATE_START_ALTERNATIVE':'晚上午开放 替代景点'}
    keywords=chinese.get(need,english) if lang=='zh' else japanese if lang=='ja' else english
    return {'entity_type':kind.upper(),'entity_name':entity,'location':location,'information_need':need,
        'travel_date':g.get('travel_date'),'preferred_language':lang,'preferred_source':'OFFICIAL',
        'expected_output':english,'keywords':keywords,'origin':origin,'destination':destination,
        'date_scope':'EXACT_DATE' if exact else 'CURRENT_REFERENCE','check_in':profile.get('start_date'),
        'check_out':profile.get('end_date'),'guest_count':profile.get('traveler_count'),'room_count':1 if kind=='hotel' else None}

def quality_gate(intent,query):
    need=intent['information_need']; entity=intent.get('entity_name','')
    checks={'entity_resolved':bool(entity) and not bool(PLACEHOLDER.search(entity)),
        'intent_specific':need!='ENTITY_DISCOVERY','keywords_relevant':True,
        'language_valid':intent['preferred_language'] in {'en','ja','zh'},'location_sufficient':bool(intent.get('location')),
        'date_scope_correct':intent['date_scope']!='EXACT_DATE' or bool(intent.get('check_in') and intent.get('check_out') and intent.get('guest_count')),
        'no_placeholder_leakage':not bool(PLACEHOLDER.search(query)) and not bool(re.search(r'\b[A-Z]+_[A-Z_]+\b',query))}
    if entity and entity.casefold() not in query.casefold():checks['entity_resolved']=False
    if intent['date_scope']=='EXACT_DATE':
        checks['date_scope_correct']=checks['date_scope_correct'] and all(str(intent.get(k) or '') in query for k in ('check_in','check_out')) and f"{intent.get('guest_count')} adults" in query
        if intent.get('entity_type')=='HOTEL':checks['date_scope_correct']=checks['date_scope_correct'] and '1 room' in query
    if intent.get('entity_type')=='RESTAURANT' and re.search(r'→|/|或',entity):checks['entity_resolved']=False
    if need in {'DIRECT_WALK','PUBLIC_TRANSIT'} and (not (intent.get('origin') and intent.get('destination')) or any(PLACEHOLDER.search(str(intent.get(k,''))) for k in ('origin','destination'))):checks['entity_resolved']=False
    if need=='EXCHANGE_RATE' and re.search(r'opening|reservation|営業時間|予約|徒歩|入場',query,re.I):checks['keywords_relevant']=False
    if 'FLIGHT' in need and re.search(r'walking|徒歩|入場|朝食',query,re.I):checks['keywords_relevant']=False
    if need in {'CURRENT_MENU_PRICE','ADMISSION_PRICE'} and re.search(r'weather|為替|exchange rate',query,re.I):checks['keywords_relevant']=False
    if re.search(r'official current price cost reference|\b(food|attractions) official\b|大阪为基地|京都一日往返',query,re.I):checks['keywords_relevant']=False
    unrelated={
        'OPENING_HOURS':r'料金|予約|徒歩|ticket|price|reservation|walking',
        'ADDRESS':r'営業時間|料金|予約|徒歩|opening hours|ticket|reservation',
        'FLIGHT_DURATION':r'営業時間|料金|予約|access|entrance',
        'EXCHANGE_RATE':r'アクセス|出入口|ticket|menu',
        'ENTRY_RULE':r'営業時間|料金|予約|徒歩|walking|menu',
        'EXACT_HOTEL_QUOTE':r'営業時間|アクセス|徒歩|address|check in|check out|breakfast',
    }
    if need in unrelated and re.search(unrelated[need],query,re.I):checks['keywords_relevant']=False
    return {'status':'PASS' if all(checks.values()) else 'REGENERATE_OR_RESOLVE_ENTITY','checks':checks,
            'reasons':[k for k,v in checks.items() if not v]}

def semantic_query(gaps,profile,attempt=0,plan=None):
    intent=build_intent(gaps,profile,plan,attempt)
    parts=[intent['entity_name'],'' if intent['entity_name'].endswith(intent['location']) else intent['location'],intent['keywords']]
    if intent['date_scope']=='EXACT_DATE':parts.extend([str(intent.get('check_in') or ''),str(intent.get('check_out') or ''),
        str(intent.get('guest_count') or '')+' adults', '1 room' if intent['entity_type']=='HOTEL' else ''])
    # Source class changes after a failed class, but never adds unrelated facts.
    parts.append('公式' if intent['preferred_language']=='ja' else '官网' if intent['preferred_language']=='zh' else 'official')
    if intent['date_scope']=='EXACT_DATE' and attempt:parts.append('Booking.com' if intent['entity_type']=='HOTEL' else 'airline OTA')
    query=' '.join(dict.fromkeys(p for p in parts if p)).strip()[:500]
    return {'query':query,'language':intent['preferred_language'],'query_class':'local_language' if intent['preferred_language'] in {'ja','zh'} else 'official' if not attempt else 'fallback',
            'category':gaps[0]['category'],'intent':intent,'quality_gate':quality_gate(intent,query)}
