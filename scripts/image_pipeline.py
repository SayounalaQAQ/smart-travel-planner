"""Bounded Commons discovery, license verification, download and attraction binding."""
import argparse
import hashlib
import json
import re
import sys
import html
from datetime import datetime,timezone
from urllib.parse import urlsplit,unquote
from html.parser import HTMLParser
from pathlib import Path
from runtime_paths import resolve_plugin_root, output_directory

LICENSE=re.compile(r'^(CC0(?: 1\.0)?|Public domain|CC BY(?:-SA)? \d+(?:\.\d+)?)$',re.I)

def _license_url(value):
    match=re.fullmatch(r'https://creativecommons.org/(licenses/(by(?:-sa)?)/(\d+\.\d+)/|publicdomain/zero/1\.0/)',str(value))
    if not match:return None
    return 'CC '+match[2].upper().replace('BY-SA','BY-SA')+' '+match[3] if match[2] else 'CC0 1.0'

class _ImagePage(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.chunks=[];self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('type')=='application/ld+json':self.active=True;self.chunks=[]
    def handle_data(self,data):
        if self.active:self.chunks.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            self.active=False
            try:self.blocks.append(json.loads(''.join(self.chunks)))
            except ValueError:pass

def licensed_page_image(body,image_url):
    """Accept only an image-specific JSON-LD license, never a page footer disclaimer."""
    parser=_ImagePage();parser.feed(body)
    def nodes(value):
        if isinstance(value,list):
            for x in value:yield from nodes(x)
        elif isinstance(value,dict):
            kind=value.get('@type');kinds=kind if isinstance(kind,list) else [kind]
            if 'ImageObject' in kinds:yield value
            for child in value.values():
                if isinstance(child,(dict,list)):yield from nodes(child)
    for node in nodes(parser.blocks):
        if node.get('contentUrl')!=image_url:continue
        license_name=_license_url(node.get('license'))
        creator=node.get('creator') or node.get('author');author=creator.get('name') if isinstance(creator,dict) else creator
        if license_name and isinstance(author,str) and author.strip():
            from visual_sources import PhotoPage
            page=PhotoPage();page.feed(body)
            same_photo=page.meta.get('og:image')==image_url
            return {'title':str(node.get('name') or (page.meta.get('og:title') if same_photo else '') or ''),'description':str(node.get('description') or (page.meta.get('og:description') if same_photo else '') or ''),'author':author,
                    'license':license_name,'license_url':node['license'],'image_url':image_url}
    raise ValueError('No image-specific open license and author in original page; discovery or copyright disclaimers are not permission')

def verify_supplied_images(plan,image_dir,*,service=None,page_loader=None):
    """Re-read original metadata; normalize only permitted images into controlled output."""
    root=resolve_plugin_root();destination=Path(image_dir).resolve();destination.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(root/'mcp-server/src'))
    if service is None:import server as service
    from security.network import request_bytes
    from PIL import Image,ImageOps
    requirements={r['attraction_id']:r for r in image_requirements(plan)}
    accepted=[];rejected=[]
    for original in plan.get('images',[])[:6]:
        row=dict(original)
        try:
            identifier=row.get('attraction_id') or next((k for k,r in requirements.items() if row.get('attraction')==r['name']),None)
            if identifier not in requirements:raise ValueError('Not bound to a selected core attraction')
            req=requirements[identifier];page=str(row.get('page_url') or '')
            if not row.get('image_url'):raise ValueError('Original image URL required; a local file and license label are not provenance')
            if page.startswith('https://commons.wikimedia.org/wiki/File:'):
                title=unquote(page.split('/wiki/',1)[1]).replace('_',' ')
                found=service.commons_images(title,location='')
                metadata=next((x for x in found.get('results',[]) if unquote(str(x.get('page_url'))).replace('_',' ')==unquote(page).replace('_',' ') and eligible_image(x,req)['eligible']),None)
                if not metadata:raise ValueError('Original Commons metadata unavailable or license/identity not verified')
                meta={**metadata,'author':html.unescape(re.sub('<[^>]+>','',str(metadata.get('artist') or metadata.get('author') or '')))}
                if row.get('image_url') and row['image_url']!=meta.get('image_url'):raise ValueError('Image URL does not match original licensed image metadata')
            else:
                if not page.startswith('https://'):raise ValueError('Public HTTPS original image page required')
                body=page_loader(page) if page_loader else request_bytes(page,timeout=8,max_bytes=1_000_000,content_types={'text/html'})
                if isinstance(body,tuple):body=body[0].decode(body[2],errors='replace')
                meta=licensed_page_image(body,row.get('image_url'))
                identity=(meta['title']+' '+meta['description']).casefold()
                if not any(str(a).casefold() in identity for a in req['aliases'] if len(str(a))>=2):raise ValueError('Image identity does not match attraction')
                if not image_context_matches(meta['title'],req):raise ValueError('Image is a namesake transit facility, not the selected attraction')
            if not meta.get('author'):raise ValueError('Original source author required')
            source=Path(row.get('local_path',''))
            target=destination/(hashlib.sha256((identifier+page).encode()).hexdigest()[:24]+'.jpg')
            if source.is_file():
                if not row.get('sha256') or hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Existing image file lacks a matching integrity hash')
                if row.get('image_url')!=meta.get('image_url'):raise ValueError('Existing file requires matching original image provenance')
            # A host-provided hash proves local integrity, not that the pixels are
            # the licensed image. Acquire pixels from the verified source URL.
            raw=request_bytes(meta['image_url'],timeout=8,max_bytes=12_000_000,content_types={'image/jpeg','image/png','image/webp'})[0]
            import io
            with Image.open(io.BytesIO(raw)) as probe:probe.verify()
            with Image.open(io.BytesIO(raw)) as probe:
                picture=ImageOps.exif_transpose(probe).convert('RGB');picture.load()
                if max(picture.size)<900 or min(picture.size)<400:raise ValueError('Image below usable resolution')
                picture.save(target,format='JPEG',quality=90);width,height=picture.size
            row.update(local_path=str(target),image_url=meta['image_url'],page_url=page,license=meta['license'],license_url=meta.get('license_url'),author=meta['author'],
                       title=meta['title'],attraction_id=identifier,attraction=req['name'],width=width,height=height,
                       license_verified=True,identity_verified=True,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                       source_verification={'status':'VERIFIED','method':'Commons metadata' if 'commons.wikimedia.org' in page else 'original-page ImageObject JSON-LD',
                           'page_url':page,'checked_at':datetime.now(timezone.utc).isoformat(),'redistribution_license':meta['license']},
                       transformations=['EXIF orientation','JPEG RGB conversion'])
            row.setdefault('caption',req['name']+' 历史实拍参考，不是旅行当日实况')
            accepted.append(row)
        except Exception as exc:rejected.append({'attraction_id':row.get('attraction_id'),'page_url':row.get('page_url'),'reason':type(exc).__name__+': '+str(exc)[:250]})
    return {'images':accepted,'rejected':rejected,'status':'PASS' if accepted and not rejected else 'PARTIAL' if accepted else 'UNAVAILABLE'}


def attraction_id(item):
    return str(item.get('id') or item.get('place_id') or hashlib.sha256(str(item.get('name','')).encode()).hexdigest()[:12])


def image_requirements(plan,max_images=6):
    if not 0<=max_images<=6:raise ValueError('max_images must be 0..6')
    requirements=[]
    from trip_entities import selected_attractions
    for item in selected_attractions(plan):
        if item.get('core',True) is False:continue
        requirements.append({'attraction_id':attraction_id(item),'name':item['name'],
            'aliases':list(dict.fromkeys([item['name'],*item.get('image_aliases',[])])),
            'location':item.get('image_location') or plan.get('trip_profile',{}).get('destination',''),
            'event':bool(item.get('event')),'excluded_subjects':item.get('image_excluded_subjects',[]),'status':'NOT_RESEARCHED'})
        if len(requirements)>=max_images:break
    return requirements if max_images else []


def eligible_image(item,requirement):
    license_ok=bool(LICENSE.fullmatch(str(item.get('license',''))))
    page=str(item.get('page_url',''))
    provenance=page.startswith('https://commons.wikimedia.org/wiki/File:')
    attribution=bool(item.get('artist') or item.get('author')) or item.get('license','').lower() in {'public domain','cc0','cc0 1.0'}
    identity=(str(item.get('title',''))+' '+str(item.get('description',''))).casefold()
    aliases=[str(a).casefold() for a in requirement['aliases'] if len(str(a))>=3]
    matches=[a for a in aliases if a in identity]
    dims=[item.get('width'),item.get('height')]
    quality=all(isinstance(x,(int,float)) for x in dims) and max(dims)>=900 and min(dims)>=400
    context_ok=image_context_matches(item.get('title',''),requirement)
    return {'eligible':license_ok and provenance and attribution and bool(matches) and quality and context_ok,
            'license_verified':license_ok,'provenance_verified':provenance,'author_present':attribution,
            'identity_matches':matches,'resolution_sufficient':quality,'subject_context_matches':context_ok}


def image_context_matches(title,requirement):
    """A namesake station is not a photograph of the attraction itself."""
    transit=re.compile(r'\b(?:station|concourse|platform|metro|sta\s+l\d+)\b|地铁|站厅|站台',re.I)
    aliases=' '.join(str(x) for x in requirement['aliases'])
    if transit.search(str(title)) and not transit.search(aliases):return False
    return not any(str(x).casefold() in str(title).casefold() for x in requirement.get('excluded_subjects',[]))


def collect_images(plan,image_dir=None,*,selections=None,max_images=6,service=None):
    root=resolve_plugin_root();destination=Path(image_dir or output_directory()/'images').resolve()
    live=service is None
    if service is None:
        sys.path.insert(0,str(root/'mcp-server/src'))
        import server as service
    requirements=image_requirements(plan,max_images)
    selections=selections if selections is not None else plan.get('image_selections',[])
    identifiers={r['attraction_id'] for r in requirements}
    images=verify_supplied_images(plan,destination,service=service)['images'] if plan.get('images') else []
    alternatives=[x for x in selections if x.get('page_url') and not str(x['page_url']).startswith('https://commons.wikimedia.org/')]
    if alternatives:images.extend(verify_supplied_images({**plan,'images':alternatives[:2]},destination,service=service)['images'])
    attempts=list(plan.get('image_pipeline',{}).get('attempts',[]))
    references=[]
    import time
    deadline=time.monotonic()+90
    commons_available=plan.get('image_source_policy',{}).get('commons_enabled',True)
    for req in requirements:
        supplied=[x for x in selections if x.get('attraction_id')==req['attraction_id']]
        if any(x.get('attraction_id')==req['attraction_id'] for x in images) and not any(x.get('file_title') for x in supplied):
            req['status']='DOWNLOADED';continue
        used=sum(x.get('attraction_id')==req['attraction_id'] and x.get('provider')=='Wikimedia Commons' for x in attempts)
        if used>=4:
            req.update(status='UNAVAILABLE',failure_reason='Commons attempt budget exhausted; alternative source budget remains')
        # Host discovered file titles still need fresh Commons metadata; never trust host license strings.
        queries=[str(x['file_title']) for x in supplied if str(x.get('file_title','')).startswith('File:')][:2]
        if not queries:queries=[req['aliases'][0],req['aliases'][-1]+' '+req['location']][:2]
        tried={x.get('query') for x in attempts if x.get('attraction_id')==req['attraction_id']}
        queries=[q for q in dict.fromkeys(queries) if q not in tried][:max(0,min(2,4-used))] if commons_available else []
        downloaded=False
        for query in list(dict.fromkeys(queries)):
            if time.monotonic()>deadline:break
            entry={'attraction_id':req['attraction_id'],'query':query,'provider':'Wikimedia Commons','status':'ATTEMPTED'}
            attempts.append(entry)
            try:
                found=service.commons_images(query,location='' if query.startswith('File:') else req['location'])
                choices=[]
                for row in found.get('results',[]):
                    check=eligible_image(row,req)
                    entry.setdefault('candidate_checks',[]).append({'title':row.get('title'),**check})
                    if check['eligible']:choices.append((row,check))
                entry['status']='RESULTS' if found.get('results') else 'EMPTY'
                for row,check in choices[:2]:
                    try:
                        filename=hashlib.sha256((req['attraction_id']+row['title']).encode()).hexdigest()[:24]+'.jpg'
                        image=service.download_image(row['image_id'],filename,output_root=destination)
                        from PIL import Image,ImageOps
                        with Image.open(image['local_path']) as probe:probe.verify()
                        with Image.open(image['local_path']) as probe:
                            picture=ImageOps.exif_transpose(probe).convert('RGB')
                            if max(picture.size)<900 or min(picture.size)<400:raise ValueError('Low resolution download')
                            picture.save(image['local_path'],format='JPEG',quality=90)
                            image['width'],image['height']=picture.size
                        image.update(attraction_id=req['attraction_id'],attraction=req['name'],author=image.get('author') or image.get('artist'),
                            license_verified=True,identity_verified=True,match_basis=check['identity_matches'],
                            caption=req['name']+(' 历史实拍示意 不代表目标年份活动' if req['event'] else ' 地点实拍'),
                            transformations=['EXIF orientation','JPEG RGB conversion'],
                            source_verification={'status':'VERIFIED','method':'Commons metadata','page_url':row['page_url'],
                                'checked_at':found.get('checked_at') or datetime.now(timezone.utc).isoformat(),'redistribution_license':row['license']},
                            sha256=hashlib.sha256(Path(image['local_path']).read_bytes()).hexdigest())
                        images=[x for x in images if x.get('attraction_id')!=req['attraction_id']]
                        images.append(image);req['status']='DOWNLOADED';entry['download_status']='PASS';downloaded=True;break
                    except Exception as exc:
                        entry.setdefault('download_errors',[]).append(type(exc).__name__+': '+str(exc)[:250])
                if downloaded:break
            except Exception as exc:
                entry.update(status='FAILED',failure_reason=type(exc).__name__+': '+str(exc)[:300])
                # A connection-wide TLS failure should not spend every attraction's
                # budget repeating the same dead endpoint. Alternative sources follow.
                if any(t in str(exc).lower() for t in ('handshake','ssl','timed out','connection')):
                    commons_available=False;break
        if not downloaded:
            if live and time.monotonic()<deadline:
                from visual_sources import discover_fallback
                fallback=discover_fallback({**plan,'image_selections':selections},req,destination,service)
                images.extend(fallback['images']);references.extend(fallback['references']);attempts.extend(fallback['attempts'])
            embedded=any(x.get('attraction_id')==req['attraction_id'] for x in images)
            linked=any(x['attraction_id']==req['attraction_id'] and x['photo_match']=='VERIFIED' for x in references)
            req['visual_status']='EMBEDDED_LICENSED' if embedded else 'EXTERNAL_PHOTO_REFERENCES' if linked else 'NO_VERIFIED_VISUAL_SOURCE'
            req['status']='DOWNLOADED' if embedded else 'UNAVAILABLE'
            req['fallback']='See bound external photo references; unknown licenses are never embedded.'
        else:req['visual_status']='EMBEDDED_LICENSED'
    for req in requirements:
        req.setdefault('visual_status','EMBEDDED_LICENSED' if any(x.get('attraction_id')==req['attraction_id'] for x in images) else 'NO_VERIFIED_VISUAL_SOURCE')
    images=list({x['attraction_id']:x for x in images}.values())
    return {'images':images,'requirements':requirements,'attempts':attempts,'image_directory':str(destination),
            'photo_references':references,'capabilities':{'commons': 'available' if any(a.get('provider')=='Wikimedia Commons' and a.get('status')=='RESULTS' for a in attempts) else 'unavailable',
                'openverse':'available' if any(a.get('provider')=='Openverse' and a.get('status')=='RESULTS' for a in attempts) else 'unavailable',
                'host_candidates':bool(selections),'original_page_reading':'available' if references else 'not_verified'},
            'status':'PASS' if requirements and len(images)==len(requirements) else 'PARTIAL' if images or any(r.get('photo_match')=='VERIFIED' for r in references) else 'UNVERIFIED' if references else 'UNAVAILABLE',
            'limits':{'max_images':max_images,'queries_per_run_per_attraction':2,'total_queries_per_attraction':4,'downloads_per_query':2,
                'openverse_queries_per_attraction_per_run':1,'openverse_queries_per_attraction_total':2,
                'license_candidates_per_attraction':2,'reference_pages_per_attraction':3,'reference_reads_per_page_total':2,
                'soft_run_deadline_seconds':90,'request_timeout_seconds':8}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    p.add_argument('--image-dir');p.add_argument('--selections');p.add_argument('--max-images',type=int,default=6);a=p.parse_args()
    plan=json.loads(Path(a.input).read_text(encoding='utf-8'))
    selections=json.loads(Path(a.selections).read_text(encoding='utf-8')) if a.selections else []
    result=collect_images(plan,a.image_dir,selections=selections,max_images=a.max_images)
    plan['images']=result['images'];plan['image_pipeline']=result
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='images'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
