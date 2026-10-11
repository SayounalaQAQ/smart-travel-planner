#!/usr/bin/env python3
"""Safe setup helper for a bundled server; no third-party downloads or host mutations."""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; server=root/'mcp-server/src/server.py'
mode='A' if '--auto' in sys.argv else ('B' if '--confirm' in sys.argv else 'C')
if '--disabled' in sys.argv: mode='C'
message={'A':'Bundled stdlib source is present. Run a local MCP handshake and tool-discovery check; the installed plugin manifest lets the host start it.', 'B':'Ask the user before enabling the bundled local server in host MCP settings.', 'C':'Do not install/start MCP; continue with Skill, native search, and local scripts.'}[mode]
result={'mode':mode,'message':message,'server_source':str(server),'command':[sys.executable,str(server)],'external_downloads':False,'automatic_host_config_changes':False}
if mode=='A':
 wire='\n'.join([json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'installer','version':'0'}}}),json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}),json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'health_check','arguments':{}}})])+'\n'
 proc=subprocess.run([sys.executable,str(server)],input=wire,text=True,capture_output=True,timeout=90)
 try:
  replies=[json.loads(x) for x in proc.stdout.splitlines()]; count=len(replies[1]['result']['tools']); provider_health=replies[2]['result'].get('structuredContent',{}).get('data',{}); result['health_check']='passed' if count==13 and provider_health.get('providers') else 'failed'; result['tools_discovered']=count; result['provider_health']=provider_health
 except Exception as exc: result['health_check']='failed'; result['error']=str(exc); sys.exit(1)
print(json.dumps(result,indent=2))
if mode=='A' and result.get('health_check')!='passed': sys.exit(1)
