#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; server=root/'mcp-server/src/server.py'
checks={'plugin_manifest':(root/'plugin.json').is_file(),'mcp_manifest':(root/'mcp.json').is_file(),'skill':(root/'skills/smart-travel-planner/SKILL.md').is_file(),'server':server.is_file(),
        'skill_entry':(root/'skills/smart-travel-planner/scripts/plugin_entry.py').is_file(),
        'standard_docx_generator':(root/'scripts/build_docx.py').is_file(),
        'delivery_pipeline':(root/'scripts/deliver_plan.py').is_file(),
        'image_pipeline':(root/'scripts/image_pipeline.py').is_file(),
        'requirements':(root/'requirements-docx.txt').is_file(),
        'references':all((root/'skills/smart-travel-planner/references'/name).is_file() for name in ('experience-discovery.md','image-policy.md','document-spec.md'))}
messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'verify','version':'1'}}},{'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'health_check','arguments':{}}}]
r=subprocess.run([sys.executable,str(root/'installer/start_mcp.py')],input=''.join(json.dumps(x)+'\n' for x in messages),text=True,capture_output=True,timeout=40)
try:
    lines=[json.loads(x) for x in r.stdout.splitlines()]; checks['mcp_initialize']=lines[0].get('result',{}).get('serverInfo',{}).get('name')=='smart-travel-mcp'; checks['mcp_tools_discoverable']=len(lines[1].get('result',{}).get('tools',[]))==13; checks['mcp_health_check_responds']=bool(lines[2].get('result',{}).get('structuredContent',{}).get('data',{}).get('providers'))
    manifest=json.loads((root/'plugin.json').read_text(encoding='utf-8'))
    checks['mcp_version_matches_manifest']=lines[0].get('result',{}).get('serverInfo',{}).get('version')==manifest['version']
except Exception as e: checks.update(mcp_initialize=False,mcp_tools_discoverable=False,mcp_health_check_responds=False,error=str(e))
print(json.dumps(checks,indent=2)); sys.exit(not all(checks.values()))
