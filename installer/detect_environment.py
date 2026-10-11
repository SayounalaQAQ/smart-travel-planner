#!/usr/bin/env python3
"""Runtime capability inventory; detection never installs packages."""
import importlib.util,json,os,shutil,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
providers=json.loads((root/'config/providers.json').read_text(encoding='utf-8')).get('providers',{})
provider_caps={name:{'configured':bool((item.get('primary') or {}).get('base_url') or (item.get('primary') or {}).get('type') in {'agent','manual'}),
                     'reachable':None,'capability':item.get('capability','unknown'),
                     'provider':(item.get('primary') or {}).get('name'),
                     'fallback':(item.get('fallback') or {}).get('name')}
               for name,item in providers.items()}
caps={'runtime':{'python_available':sys.version_info>=(3,10),'python_version':sys.version.split()[0],'node_available':shutil.which('node') is not None,'web_search':{'available':None,'source':'host runtime must report'},'browser':{'available':None,'source':'host runtime must report'},'image_support':{'available':None,'source':'host runtime must report'},'file_support':{'available':None,'source':'host runtime must report'},'docx_library_available':importlib.util.find_spec('docx') is not None,'image_processing_library_available':importlib.util.find_spec('PIL') is not None},'plugin':{'skill_source_present':(root/'skills/smart-travel-planner/SKILL.md').is_file(),'mcp_source_present':(root/'mcp-server/src/server.py').is_file(),'mcp_runtime_compatible':sys.version_info>=(3,10)},'providers':provider_caps,'reachability_note':'Provider reachability is deliberately not guessed here; use MCP health_check for bounded live probes.'}
print(json.dumps(caps,indent=2));
