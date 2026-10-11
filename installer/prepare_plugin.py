#!/usr/bin/env python3
"""Check local runtime; optionally pin a discovered Python in extracted plugin configs."""
import argparse
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from runtime_paths import doctor, python_runtime

def main():
    p=argparse.ArgumentParser();p.add_argument('--configure-runtime',action='store_true');p.add_argument('--python');a=p.parse_args()
    runtime=python_runtime(a.python);result=doctor(root)
    if a.configure_runtime:
        for name in ('.mcp.json','mcp.json','adapters/codex/mcp.json'):
            path=root/name;data=json.loads(path.read_text(encoding='utf-8'))
            data['mcpServers']['smart-travel-mcp']['command']=runtime
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        result['local_plugin_runtime_configured']=True
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
