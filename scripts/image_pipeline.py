"""Bounded Commons discovery, license verification, download and attraction binding."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from runtime_paths import resolve_plugin_root, output_directory

LICENSE=re.compile(r'^(CC0(?: 1\.0)?|Public domain|CC BY(?:-SA)? \d+(?:\.\d+)?)$',re.I)


def attraction_id(item):
    return str(item.get('id') or item.get('place_id') or hashlib.sha256(str(item.get('name','')).encode()).hexdigest()[:12])


def image_requirements(plan,max_images=6):
    if not 0<=max_images<=6:raise ValueError('max_images must be 0..6')
    requirements=[]
    for item in plan.get('attractions',[]):
        if item.get('core',True) is False:continue
        requirements.append({'attraction_id':attraction_id(item),'name':item['name'],
            'aliases':list(dict.fromkeys([item['name'],*item.get('image_aliases',[])])),
            'location':item.get('image_location') or plan.get('trip_profile',{}).get('destination',''),
            'event':bool(item.get('event')),'status':'NOT_RESEARCHED'})
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
    return {'eligible':license_ok and provenance and attribution and bool(matches) and quality,
            'license_verified':license_ok,'provenance_verified':provenance,'author_present':attribution,
            'identity_matches':matches,'resolution_sufficient':quality}


def collect_images(plan,image_dir=None,*,selections=None,max_images=6,service=None):
    root=resolve_plugin_root();destination=Path(image_dir or output_directory()/'images').resolve()
    if service is None:
        sys.path.insert(0,str(root/'mcp-server/src'))
        import server as service
    requirements=image_requirements(plan,max_images);selections=selections or []
    identifiers={r['attraction_id'] for r in requirements}
    images=[dict(x) for x in plan.get('images',[]) if x.get('attraction_id') in identifiers and Path(x.get('local_path','')).is_file()]
    attempts=list(plan.get('image_pipeline',{}).get('attempts',[]))
    for req in requirements:
        supplied=[x for x in selections if x.get('attraction_id')==req['attraction_id']]
        if any(x.get('attraction_id')==req['attraction_id'] for x in images) and not supplied:
            req['status']='DOWNLOADED';continue
        used=sum(x.get('attraction_id')==req['attraction_id'] for x in attempts)
        if used>=4:
            req.update(status='UNAVAILABLE',failure_reason='Four-attempt image research budget exhausted');continue
        # Host discovered file titles still need fresh Commons metadata; never trust host license strings.
        queries=[str(x['file_title']) for x in supplied if str(x.get('file_title','')).startswith('File:')][:2]
        if not queries:queries=[req['aliases'][0],req['aliases'][-1]+' '+req['location']][:2]
        tried={x.get('query') for x in attempts if x.get('attraction_id')==req['attraction_id']}
        queries=[q for q in dict.fromkeys(queries) if q not in tried][:min(2,4-used)]
        downloaded=False
        for query in list(dict.fromkeys(queries)):
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
                            sha256=hashlib.sha256(Path(image['local_path']).read_bytes()).hexdigest())
                        images=[x for x in images if x.get('attraction_id')!=req['attraction_id']]
                        images.append(image);req['status']='DOWNLOADED';entry['download_status']='PASS';downloaded=True;break
                    except Exception as exc:
                        entry.setdefault('download_errors',[]).append(type(exc).__name__+': '+str(exc)[:250])
                if downloaded:break
            except Exception as exc:
                entry.update(status='FAILED',failure_reason=type(exc).__name__+': '+str(exc)[:300])
        if not downloaded:
            req['status']='UNAVAILABLE'
            req['fallback']='Try host-native Commons discovery; exact File metadata may use the remaining four-attempt total budget. Never bypass TLS or licenses.'
    return {'images':images,'requirements':requirements,'attempts':attempts,'image_directory':str(destination),
            'status':'PASS' if requirements and len(images)==len(requirements) else 'PARTIAL' if images else 'UNAVAILABLE',
            'limits':{'max_images':max_images,'queries_per_run_per_attraction':2,'total_queries_per_attraction':4,'downloads_per_query':2}}


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
