#!/usr/bin/env python3
"""Structural release validation, distinct from a real host installation."""
import json,re
from pathlib import Path

def validate(root):
    root=Path(root).resolve();issues=[]
    def read(name):
        try:return json.loads((root/name).read_text(encoding='utf-8'))
        except (OSError,ValueError) as e:issues.append(name+': '+str(e));return {}
    portable=read('plugin.json');version=portable.get('version');name=portable.get('name')
    for path in ('.claude-plugin/plugin.json','.codex-plugin/plugin.json'):
        manifest=read(path)
        if manifest.get('name')!=name or manifest.get('version')!=version:issues.append('Manifest identity differs: '+path)
    claude=read('.claude-plugin/marketplace.json');codex=read('.agents/plugins/marketplace.json')
    for catalog,platform in ((claude,'claude'),(codex,'codex')):
        if not re.fullmatch(r'[a-z][a-z0-9-]+',str(catalog.get('name',''))):issues.append('Invalid marketplace name: '+platform)
        entries=catalog.get('plugins',[])
        if len(entries)!=1 or entries[0].get('name')!=name:issues.append('Marketplace plugin mismatch: '+platform);continue
        source=entries[0].get('source');relative=source if isinstance(source,str) else (source or {}).get('path')
        resolved=(root/(relative or '__missing__')).resolve()
        if relative!='./' or resolved!=root or not (resolved/'plugin.json').is_file():issues.append('Marketplace source must resolve full root: '+platform)
    if claude.get('name')!=codex.get('name') or not claude.get('owner',{}).get('name'):issues.append('Catalog identity/owner invalid')
    for path,variable in (('.mcp.json','${CLAUDE_PLUGIN_ROOT}'),('mcp.json','${PLUGIN_ROOT}'),('adapters/codex/mcp.json','${PLUGIN_ROOT}')):
        cfg=read(path).get('mcpServers',{}).get('smart-travel-mcp',{})
        if cfg.get('args')!=[variable+'/installer/start_mcp.py']:issues.append('MCP root args incorrect: '+path)
        if not cfg.get('command'):issues.append('MCP runtime missing: '+path)
    dependencies=read('config/dependencies.json').get('dependencies',[])
    if next((d.get('version') for d in dependencies if d.get('name')=='smart-travel-mcp'),None)!=version:issues.append('Dependency version differs')
    release=read('config/release.json')
    if release.get('version')!=version or release.get('tag')!='v'+str(version):issues.append('Release version/tag differs')
    required=('LICENSE','README.md','README-BEGINNER.md','README-ADVANCED.md','README-AI-INSTALL.md','CHANGELOG.md','SECURITY.md',
              'scripts/deliver_plan.py','scripts/image_pipeline.py','scripts/build_docx.py','requirements-docx.txt',
              'installer/start_mcp.py','skills/smart-travel-planner/scripts/plugin_entry.py','mcp-server/src/server.py')
    issues.extend('Missing '+p for p in required if not (root/p).is_file())
    skill=root/'skills/smart-travel-planner/SKILL.md'
    if skill.is_file():
        header=skill.read_text(encoding='utf-8').split('---',2)[1]
        if 'name: smart-travel-planner' not in header or 'travel planning' not in header:issues.append('Skill trigger metadata missing')
    return {'structural_status':'PASS' if not issues else 'FAIL','issues':issues,'version':version,'plugin':name,
            'marketplace':claude.get('name'),'claude_persistent_installation':'NOT_TESTED','codex_gui_installation':'NOT_TESTED',
            'doubao_host_installation':'NOT_TESTED','configuration_only':True}

if __name__=='__main__':
    result=validate(Path(__file__).resolve().parents[1]);print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(bool(result['issues']))
