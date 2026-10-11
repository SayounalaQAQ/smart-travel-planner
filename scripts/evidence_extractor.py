"""Agent extracts meaning; deterministic validation limits evidence to opened pages.

This validates provenance, literal support and typed boundaries, not arbitrary semantic
entailment. Host Agent must inspect subject/branch/date before submitting a claim.
Search snippets cannot enter the backfill. No web data is executable.
"""
import ipaddress
import json
import re
from urllib.parse import urlsplit
from research_ledger import identity
from source_ranker import rank_source
from data_freshness import freshness

BAD=re.compile(r'ignore\s+(?:all\s+)?previous\s+instructions|paste\s+(?:your\s+)?api\s+key|run\s+(?:this\s+)?command',re.I)
FIELDS={'opening_hours','ticket_price','reservation_required','transport_info','address',
 'nearest_station','check_in_out','room_categories','breakfast','name','cuisine',
 'reservation','price_reference','backup','airport_pairs','duration_reference','climate',
 'entry','rate','amount','route_segment','exact_quote','backup_address','backup_opening','backup_cuisine','backup_price_reference',
 'cost_reference','coordinates','closing_days','photography_restrictions','recommended_duration'}

def public_url(url):
    p=urlsplit(url)
    host=(p.hostname or '').lower()
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443): return False
    if '.' not in host or host=='localhost' or host.endswith(('.example','.test','.invalid')) or host in {'example.com','example.org','example.net'}: return False
    try: return ipaddress.ip_address(host).is_global
    except ValueError: return True

def normalized(text): return re.sub(r'\s+',' ',str(text)).strip()

def extract_evidence(task,response,*,now=None):
    if response.get('task_id')!=task['task_id'] or response.get('query')!=task['query']:
        raise ValueError('Response must match issued task and exact query')
    pages={p.get('url'):p for p in response.get('pages',[]) if p.get('status')=='OPENED'}
    accepted=[]; rejected=[]
    for claim in response.get('claims',[]):
        try:
            field=claim['field']; page=pages.get(claim['source_url']); quote=normalized(claim['quote'])
            if field not in FIELDS or not page or not public_url(claim['source_url']):
                raise ValueError('Field/URL lacks an opened public page')
            if page.get('content_origin')!='PAGE_BODY' or not page.get('raw_artifact'):
                raise ValueError('Search snippet or missing raw capture')
            if not quote or quote not in normalized(page.get('text','')) or BAD.search(quote):
                raise ValueError('Unsupported literal passage or instruction-like claim')
            retrieved=page['retrieved_at']
            kind='route' if field=='route_segment' else 'exchange' if field=='rate' else 'attraction_static'
            if freshness({'retrieved_at':retrieved},kind,now=now)['refresh_required']:
                raise ValueError('Expired page needs refresh')
            value=claim['value']
            if field=='route_segment':
                if not isinstance(value,dict) or not all(value.get(k) for k in ('from_place_id','to_place_id','mode','boundary')):
                    raise ValueError('Route needs explicit endpoints/mode/boundary')
                duration=value.get('duration_minutes')
                number_words={5:'five',10:'ten'}
                if duration is not None and (not isinstance(duration,(int,float)) or isinstance(duration,bool) or duration<0 or (str(int(duration)) not in quote and number_words.get(duration,'<absent>') not in quote)):
                    raise ValueError('Route minutes must be supported in literal passage')
                if value.get('mode')!='WALK' and not all(value.get(k) for k in ('operator','line')):
                    raise ValueError('Transit operator and line required')
                if value.get('reversed') and not value.get('limitations'):
                    raise ValueError('Reverse-direction assumption must be explicit')
                for number in ('fare','distance_meters'):
                    if value.get(number) is not None and (not isinstance(value[number],(int,float)) or isinstance(value[number],bool) or value[number]<0 or str(value[number]).removesuffix('.0') not in quote.replace(',','')):
                        raise ValueError('Optional route metric absent from literal passage')
            elif field=='cost_reference':
                if not isinstance(value,dict) or not all(value.get(k) for k in ('category','item','currency','scope')):
                    raise ValueError('Typed item/currency/scope required for price reference')
                amount=value.get('amount')
                free=amount==0 and bool(re.search(r'\bFree\b|無料',quote,re.I))
                if not isinstance(amount,(int,float)) or isinstance(amount,bool) or amount<0 or (str(amount).removesuffix('.0') not in quote.replace(',','') and not free):
                    raise ValueError('Reference amount absent from supporting passage')
                if value['currency']=='JPY' and not free and not re.search(r'円|JPY|¥|￥|\byen\b|\dyen',quote,re.I):raise ValueError('JPY currency not supported')
                if value['category'] not in {'transit','attractions','food','airport_transfer','internet','insurance','hotel','flight','visa_related','misc'}:raise ValueError('Unsupported reference category')
                if normalized(value['item']) not in quote:raise ValueError('Price item absent from passage')
                if value['scope'] not in {'PER_MEAL','PER_ITEM','PER_TICKET','PER_RIDE','PER_NIGHT','PER_PACKAGE','ROUND_TRIP_REFERENCE'}:
                    raise ValueError('Only item-level planning scopes allowed')
            elif field=='coordinates':
                if not isinstance(value,dict) or not all(k in value for k in ('latitude','longitude')):raise ValueError('Coordinates required')
                if not -90<=value['latitude']<=90 or not -180<=value['longitude']<=180:raise ValueError('Invalid coordinates')
                if any(str(value[k]) not in quote for k in ('latitude','longitude')):raise ValueError('Coordinates not present in source')
            elif field=='exact_quote':
                # Kept subject/date/party/scope validation in the established contract.
                if not isinstance(value,dict): raise ValueError('Quote must use existing typed contract')
                from cost_ledger import validate_quote
                verdict=validate_quote(value,claim['quote_kind'],response['trip_profile'],now=now)
                if verdict['status']!='VERIFIED': raise ValueError('Exact date quote contract not satisfied')
                if rank_source(claim['source_url'])['tier']>2: raise ValueError('Unreliable quote source')
                body=normalized(page['text'])
                needed=['check_in','check_out','property','room_type','total_price'] if claim['quote_kind']=='hotel' else ['outbound_date','return_date','fare']
                if any(str(value.get(k,'')) not in body or value.get(k) is None for k in needed):
                    raise ValueError('Date/property/room/price not actually present on opened page')
            elif not isinstance(value,(str,int,float)) or (isinstance(value,str) and normalized(value) not in quote):
                raise ValueError('Scalar value must occur in the quoted passage')
            if field not in {'route_segment','exact_quote','cost_reference','coordinates'} and isinstance(value,(int,float)) and str(value) not in quote:
                raise ValueError('Unsupported numeric value')
            applicability=claim.get('applicable_date') or 'CURRENT_OPERATION'
            if applicability not in {'CURRENT_OPERATION','HISTORICAL_REFERENCE'} and str(applicability) not in normalized(page['text']):
                raise ValueError('Target-date applicability not supported by page')
            accepted.append({'evidence_id':identity(claim['source_url'],field,claim.get('subject'),json.dumps(value,sort_keys=True,ensure_ascii=False)),
                'claim_type':field,'subject':claim.get('subject') or task['gaps'][0]['entity'],
                'value':value,'unit':claim.get('unit'),**rank_source(claim['source_url']),
                'source_title':page.get('title') or claim['source_url'],'source_url':claim['source_url'],
                'retrieved_at':retrieved,'checked_at':retrieved,'applicable_date':applicability,
                'confidence':'low' if rank_source(claim['source_url'])['tier']>=3 else 'medium','limitations':claim.get('limitations',[]),
                'supporting_quote':quote,'raw_artifact':page['raw_artifact'],
                'target':claim.get('target') or task['gaps'][0]['target'],'task_id':task['task_id'],
                'verification_level':'OPENED_PAGE_REFERENCE'})
        except (KeyError,TypeError,ValueError) as exc:
            rejected.append({'claim':claim,'reason':str(exc)})
    return accepted,rejected
