#!/usr/bin/env python3
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('input'); a=p.parse_args(); data=json.loads(Path(a.input).read_text(encoding='utf-8')); issues=[]
for i,e in enumerate(data.get('evidence',[]),1):
 for k in ('claim','source_title','source_url','checked_at','source_type','confidence'):
  if not e.get(k): issues.append(f'evidence {i}: missing {k}')
 if e.get('source_url') and not e['source_url'].startswith('https://'): issues.append(f'evidence {i}: URL should use HTTPS')
print(json.dumps({'valid':not issues,'issues':issues},ensure_ascii=False,indent=2))
raise SystemExit(bool(issues))
