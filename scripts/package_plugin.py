#!/usr/bin/env python3
"""Build a clean plugin distribution without acceptance data or local outputs."""
import hashlib,json,re,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INCLUDE_FILES={'plugin.json','mcp.json','.mcp.json','README.md','LICENSE','requirements-docx.txt',
               'README-BEGINNER.md','README-ADVANCED.md','README-AI-INSTALL.md','CHANGELOG.md','SECURITY.md',
               'THIRD-PARTY-NOTICES.md','RELEASE-NOTES-1.0.2.md','.gitignore','.env.example',
               '.agents/plugins/marketplace.json'}
INCLUDE_DIRS={'.codex-plugin','.claude-plugin','skills','mcp-server','installer','scripts','config','adapters','assets','tests'}
EXCLUDED_PARTS={'.git','__pycache__','outputs','work','acceptance','.venv'}

def distribution_files():
    files=[ROOT/name for name in INCLUDE_FILES if (ROOT/name).is_file()]
    version=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))['version']
    notes=ROOT/f'RELEASE-NOTES-{version}.md'
    if notes.is_file():files.append(notes)
    for directory in INCLUDE_DIRS:
        base=ROOT/directory
        for path in base.rglob('*'):
            relative=path.relative_to(ROOT)
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in relative.parts):continue
            if path.is_symlink():raise ValueError('Symlinks cannot be distributed: '+str(relative))
            if path.suffix in {'.pyc','.pyo','.log'} or (path.name.startswith('.env') and path.name!='.env.example') or path.name.endswith('.local'):continue
            # Only this separately attributed CC0 test image is redistributable here.
            if directory=='tests' and path.suffix.lower() in {'.jpg','.jpeg','.png'} and relative.as_posix()!='tests/fixtures/images/sensoji-cc0.jpg':continue
            if path.suffix.lower() in {'.py','.json','.md','.txt','.toml'}:
                content=path.read_text(encoding='utf-8')
                if re.search(r'(?i)(?:[CD]:[\\/](?:Users|新建文件夹)[\\/]|/[h]ome/[^/\s]+/)',content):
                    raise ValueError('Machine-specific path in release: '+str(relative))
            files.append(path)
    return sorted(set(files))

def build(output=None):
    manifest=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))
    version=manifest['version']; target=Path(output).resolve() if output else ROOT/'outputs'/f"Smart-Travel-Planner-{version}.zip"
    target.parent.mkdir(parents=True,exist_ok=True); files=distribution_files(); prefix=f"smart-travel-planner-{version}"
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files: archive.write(path,Path(prefix)/path.relative_to(ROOT))
    with zipfile.ZipFile(target) as archive:
        names=archive.namelist()
        if any('/acceptance/' in f'/{name}/' or '/outputs/' in f'/{name}/' or '/__pycache__/' in f'/{name}/' for name in names):
            target.unlink(missing_ok=True); raise ValueError('Distribution contains test or local output artifacts')
        if not any(name.endswith('skills/smart-travel-planner/SKILL.md') for name in names): raise ValueError('Skill missing from distribution')
        if not any(name.endswith('mcp-server/src/server.py') for name in names): raise ValueError('MCP source missing from distribution')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    return target

if __name__=='__main__': print(build())
