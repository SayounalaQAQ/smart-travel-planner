#!/usr/bin/env python3
"""Verify a reviewed release ZIP without extracting or executing its contents."""
import argparse,hashlib,json,re,stat,zipfile
from pathlib import Path,PurePosixPath

def verify(archive,checksum):
    archive=Path(archive);line=Path(checksum).read_text(encoding='utf-8').strip()
    match=re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?([^\r\n]+)',line)
    if not match or match[2]!=archive.name:raise ValueError('Checksum must name the exact archive basename')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=match[1].lower():raise ValueError('SHA256 mismatch; stop installation')
    with zipfile.ZipFile(archive) as z:
        members=z.infolist()
        if len(members)>512 or sum(m.file_size for m in members)>64*1024*1024:raise ValueError('Release exceeds extraction limits')
        paths=[]
        for member in members:
            path=PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename or ':' in member.filename:raise ValueError('Unsafe archive path')
            if stat.S_ISLNK(member.external_attr>>16):raise ValueError('Archive contains a symlink')
            paths.append(path)
        if len({str(p).casefold() for p in paths})!=len(paths):raise ValueError('Duplicate archive names')
        roots={p.parts[0] for p in paths if p.parts}
        if len(roots)!=1:raise ValueError('Expected one full plugin root')
        prefix=next(iter(roots));manifest=json.loads(z.read(prefix+'/plugin.json'))
        if prefix!='smart-travel-planner-'+manifest['version']:raise ValueError('Archive/version mismatch')
        for required in ('README-AI-INSTALL.md','.claude-plugin/marketplace.json','installer/validate_distribution.py',
                         'scripts/build_docx.py','scripts/image_pipeline.py','skills/smart-travel-planner/SKILL.md','mcp-server/src/server.py'):
            if prefix+'/'+required not in z.namelist():raise ValueError('Incomplete release: '+required)
        if z.testzip():raise ValueError('Corrupt ZIP member')
    return {'status':'PASS','sha256':digest,'version':manifest['version'],'root':prefix,'files':len(paths),
            'execution_performed':False,'publisher_authentication':'Requires independent trusted repository/release verification'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--sha256-file',required=True);a=p.parse_args()
    try:result=verify(a.archive,a.sha256_file)
    except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:
        print(json.dumps({'status':'FAIL','error':str(e)}));return 2
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
