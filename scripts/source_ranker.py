"""Rank exact domain boundaries. A site containing an official name is not official."""
from urllib.parse import urlsplit
from data_freshness import timestamp

OFFICIAL = {'osaka-info.jp','discover.osaka-info.jp','kyoto.travel','japan.travel',
 'choice-hotels.jp','choicehotels.com','kuromon.com','osakacastlepark.jp','osakacastle.net',
 'inari.jp','osakametro.co.jp','nankai.co.jp','westjr.co.jp','jr-odekake.net','hankyu.co.jp',
 'takoyaki-wanaka.com','ichiran.com','kinryuramen.com','kansai-airport.or.jp',
 'jal.co.jp','ana.co.jp','flypeach.com','shairport.com','china-airlines.com','ceair.com',
 'frankfurter.dev','open-meteo.com','mofa.go.jp','keihan.co.jp','metronine.osaka',
 'osaka-airport.co.jp','osaka-chuokokaido.com','kamukura.co.jp','hirano-seishoan.com','love-central.jp',
 'nezameya.com','ginpei-shinsaibashi.com','kaguraosaka.com','shinsaibashi.or.jp','houzenji.jp','tennoji-kneaders.zetton.co.jp'}
RELIABLE = {'booking.com','expedia.com','trip.com','navitime.co.jp','japantravel.navitime.com',
            'google.com','tour.ne.jp','wikimedia.org'}
MEDIA = {'japan-guide.com','timeout.com','lonelyplanet.com'}

def within(host, domain):
    return host == domain or host.endswith('.'+domain)

def rank_source(url):
    host = (urlsplit(url).hostname or '').lower()
    if any(within(host,d) for d in OFFICIAL) or host.endswith(('.go.jp','.gov','.gov.cn')):
        return {'tier':1,'source_type':'official'}
    if any(within(host,d) for d in RELIABLE): return {'tier':2,'source_type':'high'}
    if any(within(host,d) for d in MEDIA): return {'tier':3,'source_type':'medium'}
    return {'tier':4,'source_type':'unknown'}

def ranked(results):
    return sorted(results,key=lambda row:rank_source(row['url'])['tier'])

def select_evidence(records):
    """Official conflict stays visible. Same-tier unresolved disagreement is not a fact."""
    records=sorted(records,key=lambda r:(rank_source(r['source_url'])['tier'],
                   -timestamp(r['retrieved_at']).timestamp()))
    if not records: return None,[]
    best=records[0]; conflicts=[]
    for other in records[1:]:
        if other['value'] != best['value']:
            conflicts.append({'code':'SOURCE_CONFLICT','preferred':best['evidence_id'],
                'other':other['evidence_id'],'values':[best['value'],other['value']]})
    if conflicts and any(rank_source(r['source_url'])['tier']==rank_source(best['source_url'])['tier']
                         and r['value']!=best['value'] and r['retrieved_at']==best['retrieved_at'] for r in records[1:]):
        return None,[{**c,'code':'CONFLICTING_EVIDENCE'} for c in conflicts]
    return best,conflicts
