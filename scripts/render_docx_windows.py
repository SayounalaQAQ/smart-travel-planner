#!/usr/bin/env python3
"""Structural validation and optional trusted local DOCX renderer on Windows.

Rendering success does not imply a human inspected the pages. No download,
Office COM automation, installation or document execution is performed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def verify_document(path, renderer=None, output_dir=None):
    path=Path(path).resolve()
    root=Path(__file__).resolve().parents[1]
    directory=Path(output_dir).resolve() if output_dir else path.parent/(path.stem+'-render')
    directory.mkdir(parents=True,exist_ok=True)
    structural=subprocess.run([sys.executable,str(root/'scripts/validate_docx.py'),str(path)],capture_output=True,text=True,encoding='utf-8',timeout=30)
    try: structure=json.loads(structural.stdout)
    except json.JSONDecodeError: structure={'valid':False,'issues':[structural.stderr or structural.stdout]}
    result={'structural_status':'PASS' if structure.get('valid') else 'FAIL','structural_validation':structure,
            'render_status':'UNAVAILABLE','visual_status':'UNVERIFIED','overall':'PARTIAL' if structure.get('valid') else 'FAIL',
            'page_count':None,'reviewed_pages':[], 'limitations':[]}
    if not renderer or not Path(renderer).is_file():
        result['limitations'].append('No trusted local renderer supplied; pagination and visual layout unverified')
        return result
    temp=directory/'temp'; temp.mkdir(exist_ok=True)
    env=dict(os.environ,TEMP=str(temp),TMP=str(temp),PYTHONIOENCODING='utf-8')
    try:
        completed=subprocess.run([sys.executable,str(Path(renderer).resolve()),str(path),'--output_dir',str(directory),'--emit_pdf'],
                                 capture_output=True,text=True,encoding='utf-8',timeout=60,env=env)
        log=directory/'render.log'; log.write_text(completed.stdout+'\n'+completed.stderr,encoding='utf-8')
        pages=sorted(directory.glob('page-*.png'))
        result.update(render_log=str(log),render_exit_code=completed.returncode)
        if completed.returncode==0 and pages:
            result.update(render_status='RENDERED',page_count=len(pages),pages=[str(p) for p in pages])
            result['limitations'].append('Page images exist; inspect every page before claiming visual PASS')
        else:
            result['limitations'].append('Renderer failed; see render log. Visual and pagination checks remain UNVERIFIED')
    except (OSError,subprocess.TimeoutExpired) as exc:
        result['limitations'].append(str(exc))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('file'); p.add_argument('--renderer'); p.add_argument('--output-dir'); p.add_argument('--report')
    a=p.parse_args(); result=verify_document(a.file,a.renderer,a.output_dir)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.report: Path(a.report).write_text(text,encoding='utf-8')
    print(text)
    raise SystemExit(1 if result['structural_status']=='FAIL' else 0)
