"""Public image discovery and photo-page references; a search hit is never a license."""
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def fetch_html(url):
    from security.network import request_bytes
    raw, _, charset, final = request_bytes(url, timeout=7, max_bytes=2_000_000,
        headers={'User-Agent': 'SmartTravelPlanner/1.0.3 (bounded public research)'}, content_types={'text/html'})
    return raw.decode(charset, errors='replace'), final


class PhotoPage(HTMLParser):
    def __init__(self):
        super().__init__(); self.title = ''; self.in_title = False; self.images = []; self.meta = {}; self.text = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta': self.meta[d.get('property') or d.get('name')] = d.get('content', '')
        if tag == 'img': self.images.append(d)
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title += data
        self.text.append(data)


def inspect_photo_page(body, url, req):
    """Verify direct public content and image identity from HTML, not a search snippet."""
    path = urlsplit(url).path
    if path in ('', '/', '/zh/', '/en/') or re.search(r'/(search|results)(/|$)', path):
        raise ValueError('Homepage/search results are not direct photo references')
    p = PhotoPage(); p.feed(body)
    title = html.unescape(p.title or p.meta.get('og:title', ''))
    aliases = [str(x).casefold() for x in req['aliases'] if len(str(x)) >= 2]
    relevant = any(a in (title + ' ' + p.meta.get('og:description', '') + ' ' + ' '.join(p.text)).casefold() for a in aliases)
    if not relevant: raise ValueError('Original page does not identify this attraction')
    matched = [i for i in p.images if any(a in (i.get('alt', '') + ' ' + i.get('title', '')).casefold() for a in aliases)
        and i.get('src') and not re.search(r'logo|icon|avatar|sprite', i['src'], re.I)]
    # og:image without an image-specific caption is not proof that the depicted subject matches.
    return {'attraction_id': req['attraction_id'], 'title': title, 'platform': urlsplit(url).hostname,
        'url': url, 'checked_at': stamp(), 'page_status': 'ACCESSIBLE',
        'photo_match': 'VERIFIED' if matched else 'UNCONFIRMED', 'contains_matching_photos': bool(matched),
        'matching_image_count': len(matched), 'description': '原页含与景点名称匹配的图片说明；照片不复制进本手册。' if matched else '原页相关且可访问；静态页面未能确认对应照片，需打开后查看。',
        'copy_permission': 'NOT_ESTABLISHED'}


def openverse_candidates(query, req):
    from security.network import request_bytes
    url = 'https://api.openverse.org/v1/images/?' + urlencode({'q': query, 'license': 'by,by-sa,cc0,pdm', 'page_size': 3})
    raw = request_bytes(url, timeout=7, max_bytes=400_000, content_types={'application/json'})[0]
    rows = json.loads(raw).get('results', [])
    return [{'attraction_id': req['attraction_id'], 'page_url': r.get('foreign_landing_url'),
             'image_url': r.get('url'), 'discovered_via': 'Openverse', 'title': r.get('title'),
             'discovered_license': r.get('license'), 'discovery_url': url} for r in rows if r.get('foreign_landing_url')]


def discover_fallback(plan, req, image_dir, service, *, live=True, loader=fetch_html):
    """At most one aggregation query, two original license pages, three reference pages."""
    from image_pipeline import verify_supplied_images
    attempts = []; images = []; references = []
    supplied = [r for r in plan.get('image_selections', []) if r.get('attraction_id') == req['attraction_id']]
    candidates = list(supplied)
    if live:
        query = req['aliases'][-1]
        a = {'attraction_id': req['attraction_id'], 'provider': 'Openverse', 'query': query, 'checked_at': stamp()}
        prior=[x for x in plan.get('image_pipeline',{}).get('attempts',[]) if x.get('attraction_id')==req['attraction_id'] and x.get('provider')=='Openverse']
        if len(prior)<2:
            try:
                candidates += openverse_candidates(query, req); a.update(status='RESULTS', candidate_count=len(candidates))
            except Exception as e: a.update(status='FAILED', failure_reason=type(e).__name__ + ': ' + str(e)[:250])
            attempts.append(a)
    if plan.get('image_source_policy', {}).get('commons_enabled') is False:
        candidates = [r for r in candidates if urlsplit(str(r.get('page_url', ''))).hostname != 'commons.wikimedia.org']
    for row in candidates[:2]:
        if not row.get('page_url'): continue
        result = verify_supplied_images({**plan, 'images': [row]}, image_dir, service=service)
        attempts.append({'attraction_id': req['attraction_id'], 'provider': row.get('discovered_via', 'host candidates'),
            'page_url': row['page_url'], 'status': 'LICENSE_VERIFIED' if result['images'] else 'REJECTED',
            'rejected': result['rejected'], 'checked_at': stamp()})
        if result['images']: images = result['images']; break
    if images: return {'images': images, 'references': [], 'attempts': attempts}
    attraction = next(x for x in plan.get('attractions', []) if x.get('id') == req['attraction_id'] or x.get('name') == req['name'])
    pages = [r.get('url') or r.get('page_url') for r in plan.get('photo_reference_candidates', []) if r.get('attraction_id') == req['attraction_id']]
    pages += [attraction.get('photo_page_url'), attraction.get('source_url')]
    pages += [r.get('page_url') for r in candidates]
    if live and not any(pages) and hasattr(service, 'search_web'):
        try:
            found = service.search_web(req['name'] + ' 官方 实拍', language='zh')
            pages += [r.get('url') for r in found.get('results', [])[:2]]
        except Exception as e: attempts.append({'attraction_id':req['attraction_id'],'provider':'configured web search','status':'FAILED','failure_reason':str(e)[:200]})
    for url in list(dict.fromkeys(p for p in pages if p))[:3]:
        prior=[x for x in plan.get('image_pipeline',{}).get('attempts',[]) if x.get('attraction_id')==req['attraction_id'] and x.get('page_url')==url and x.get('provider')=='original photo page']
        if len(prior)>=2:continue
        a = {'attraction_id': req['attraction_id'], 'provider': 'original photo page', 'page_url': url, 'checked_at': stamp()}
        try:
            body, final = loader(url); ref = inspect_photo_page(body, final, req)
            references.append(ref); a.update(status='PHOTO_REFERENCE' if ref['photo_match']=='VERIFIED' else 'PHOTO_UNCONFIRMED')
        except Exception as e: a.update(status='FAILED', failure_reason=type(e).__name__ + ': ' + str(e)[:250])
        attempts.append(a)
    return {'images': images, 'references': references, 'attempts': attempts}
