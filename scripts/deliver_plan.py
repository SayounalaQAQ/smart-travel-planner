#!/usr/bin/env python3
"""Standard bounded delivery: plan gate, images, readiness, bundled DOCX and validation."""
import argparse
import json
import subprocess
import hashlib
from pathlib import Path
from runtime_paths import resolve_plugin_root,output_directory,python_runtime


def deliver(input_path,output_dir=None,*,text_only=False,skip_images=False,selections=None,name='Smart_Travel_Plan.docx'):
    root=resolve_plugin_root();runtime=python_runtime();destination=output_directory(output_dir)
    if Path(name).name!=name or not name.lower().endswith('.docx'):raise ValueError('Document name must be a .docx basename')
    destination.mkdir(parents=True,exist_ok=True);source=Path(input_path).resolve()
    from delivery_validation import apply_delivery_checks
    data=apply_delivery_checks(json.loads(source.read_text(encoding='utf-8')));attempts=[];errors=[]
    checked=None;generated=False;official_validated=False;image_report={}
    def run(script,arguments,timeout=75):
        command=[runtime,str(root/'scripts'/script),*map(str,arguments)]
        try:result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        except subprocess.TimeoutExpired:
            result=subprocess.CompletedProcess(command,124,json.dumps({'status':'UNAVAILABLE','errors':[{'code':'TOOL_TIMEOUT','field':script,'reason':'Bounded subprocess timeout','repair':'检查依赖与输入后有界重试'}]}),'Bounded subprocess timeout')
        attempts.append({'script':script,'command':[runtime,str(root/'scripts'/script),*map(str,arguments)],
                         'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        return result
    def finish(status,reason=None,document=None):
        if checked and checked.is_file():
            full=json.loads(checked.read_text(encoding='utf-8'))
            developer={'readiness':full.get('readiness',{}),'budget_reconciliation':full.get('budget_reconciliation',{}),
                       'route_closure':full.get('route_closure',{}),
                       'daily_routes':[{'date':d.get('date'),'route_closure':d.get('route_closure',{}),
                                        'route_chain':d.get('route_chain',[])} for d in full.get('days',[])],
                       'planning_delivery':full.get('planning_delivery',{}),
                       'lodging_continuity':full.get('lodging_continuity',{}),'required_cost_coverage':full.get('required_cost_coverage',{}),
                       'verification_priority':full.get('verification_priority',{}),
                       'visual_status':'UNVERIFIED','booking_performed':False}
            (destination/'developer-report.json').write_text(json.dumps(developer,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'status':status,'reason':reason,'document':str(document) if document else None,
                'plan':str(destination/'plan-with-readiness.json'),'image_directory':str(destination/'images'),
                'attempts':attempts,'booking_performed':False,'generated_by':'scripts/build_docx.py' if generated else None,
                'artifact_type':'PLUGIN_STANDARD' if official_validated else 'NO_VALIDATED_ARTIFACT',
                'official_validation_passed':official_validated,'errors':errors,
                'generator':next(({'path':str(root/'scripts/build_docx.py'),'sha256':hashlib.sha256((root/'scripts/build_docx.py').read_bytes()).hexdigest(),
                                  'command':a['command'],'exit_code':a['exit_code']} for a in reversed(attempts) if a.get('script')=='build_docx.py'),None),
                'image_validation':image_report,
                'visual_sources':full.get('image_pipeline',{}).get('requirements',[]) if checked and checked.is_file() else [],
                'visual_status':'UNVERIFIED','fallback':'Structured plan/text retained if DOCX cannot run'}
        report['developer_report']=str(destination/'developer-report.json') if checked and checked.is_file() else None
        if checked and checked.is_file():
            full=json.loads(checked.read_text(encoding='utf-8'))
            report.update(planning_delivery=full.get('planning_delivery'),booking_readiness=full.get('readiness',{}).get('booking_readiness','NOT_READY'),
                          budget_verified=full.get('planning_delivery',{}).get('budget_verified',False))
        if document:report['document_sha256']=hashlib.sha256(Path(document).read_bytes()).hexdigest()
        (destination/'delivery-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    if data['delivery_validation']['errors']:
        errors.extend(data['delivery_validation']['errors']);return finish('BLOCKED','PLAN_DATA_INCOMPLETE or date/budget conflict; see structured repairs')
    staged=destination/'plan.json';staged.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    gate=run('validate_trip.py',[staged])
    if gate.returncode:
        detail=json.loads(gate.stdout);errors.extend({'code':'PLAN_DATA_INCOMPLETE','field':'plan','reason':x,'repair':'修正结构后重新运行标准入口'} for x in detail.get('issues',[]))
        return finish('BLOCKED','Critical information or plan structure needs correction')
    from image_pipeline import verify_supplied_images
    image_report=verify_supplied_images(data,destination/'images') if data.get('images') and not text_only else {'images':[],'rejected':[]}
    data['images']=image_report['images']
    if not skip_images and not text_only:
        from image_pipeline import collect_images
        result=collect_images(data,destination/'images',selections=selections)
        data['images']=result['images'];data['image_pipeline']=result
        data['photo_references']=result.get('photo_references',[])
    staged=destination/'plan.json';staged.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    checked=destination/'plan-with-readiness.json'
    readiness=run('validate_plan_readiness.py',[staged,'--output',checked,'--purpose','planning'])
    if readiness.returncode:
        detail=json.loads(readiness.stdout);errors.extend(detail.get('planning_delivery',{}).get('errors',[]))
        return finish('BLOCKED','Resolve known validation failures; missing quotes alone permit provisional delivery')
    if text_only:return finish('TEXT_ONLY','User requested text-only output')
    document=destination/name
    pending=destination/('.pending-'+name)
    # Standard generator retries once. It is never replaced by generated third-party code.
    for attempt in range(2):
        built=run('build_docx.py',['--input',checked,'--output',pending,'--image-root',destination/'images'])
        if built.returncode==0:generated=True;break
        if attempt==0:
            from runtime_paths import doctor
            attempts.append({'diagnosis':doctor(root),'input_exists':checked.is_file(),
                             'output_parent_exists':document.parent.is_dir(),'image_paths':[x.get('local_path') for x in data.get('images',[])]})
    if built.returncode:return finish('DOCX_UNAVAILABLE','Bundled generator failed twice; see diagnosis and logs')
    validated=run('validate_docx.py',[pending,'--plan',checked])
    if validated.returncode:
        detail=json.loads(validated.stdout);errors.extend(detail.get('consistency_errors',[]))
        pending.unlink(missing_ok=True)
        return finish('DOCX_INVALID','Generated document failed official validation; invalid product withheld')
    official_validated=True;pending.replace(document)
    return finish('DELIVERED',document=document)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output-dir');p.add_argument('--name',default='Smart_Travel_Plan.docx')
    p.add_argument('--text-only',action='store_true');p.add_argument('--skip-images',action='store_true');p.add_argument('--image-selections');a=p.parse_args()
    selections=json.loads(Path(a.image_selections).read_text(encoding='utf-8')) if a.image_selections else None
    try:result=deliver(a.input,a.output_dir,text_only=a.text_only,skip_images=a.skip_images,selections=selections,name=a.name)
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'UNAVAILABLE','reason':type(exc).__name__+': '+str(exc)},ensure_ascii=False));return 2
    print(json.dumps({k:v for k,v in result.items() if k!='attempts'},ensure_ascii=False,indent=2))
    return 0 if result['status'] in {'DELIVERED','TEXT_ONLY'} else 2

if __name__=='__main__':raise SystemExit(main())
