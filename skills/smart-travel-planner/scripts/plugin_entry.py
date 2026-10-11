#!/usr/bin/env python3
"""Skill-local entry to fixed bundled commands; detached skills degrade explicitly."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def locate_root(explicit=None):
    value = explicit or os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ.get('PLUGIN_ROOT')
    root = Path(value).expanduser().resolve() if value else Path(__file__).resolve().parents[3]
    if not all((root/name).is_file() for name in ('plugin.json','scripts/build_docx.py','requirements-docx.txt')):
        raise ValueError('FULL_PLUGIN_REQUIRED: this detached Skill has no bundled scripts. Load the extracted full plugin; use host research/text fallback meanwhile. Do not invent another DOCX generator.')
    return root


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root'); parser.add_argument('--standalone-skills-dir')
    parser.add_argument('action', choices=('doctor','analyze','preferences','images','deliver','build','validate','readiness','budget'))
    args, rest=parser.parse_known_args()
    try:
        root=locate_root(args.plugin_root)
        sys.path.insert(0,str(root/'scripts'))
        from runtime_paths import doctor, python_runtime
        if args.action=='doctor':
            print(json.dumps(doctor(root,args.standalone_skills_dir),ensure_ascii=False,indent=2));return 0
        scripts={'analyze':'analyze_trip_request.py','preferences':'experience_discovery.py','images':'image_pipeline.py',
                 'deliver':'deliver_plan.py','build':'build_docx.py','validate':'validate_trip.py',
                 'readiness':'validate_plan_readiness.py','budget':'calculate_budget.py'}
        env=dict(os.environ,PLUGIN_ROOT=str(root),CLAUDE_PLUGIN_ROOT=str(root))
        return subprocess.run([python_runtime(),str(root/'scripts'/scripts[args.action]),*rest],env=env).returncode
    except (ValueError,OSError) as exc:
        print(json.dumps({'status':'unavailable','reason':str(exc),'fallback':'Host research and text; load full plugin to restore bundled workflow'},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
