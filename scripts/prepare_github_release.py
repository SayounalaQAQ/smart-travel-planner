#!/usr/bin/env python3
"""Export a clean GitHub-ready tree and install template; never push or publish."""
import argparse,json,re,zipfile
from pathlib import Path
from package_plugin import build,ROOT

def prepare(output_dir,repository=None):
    if repository and (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',repository)
                       or any(part in {'.','..'} for part in repository.split('/'))):raise ValueError('Use an explicit owner/repository, not a URL or command')
    destination=Path(output_dir).resolve()
    if destination.exists():raise ValueError('Output must be a new directory; existing data will not be overwritten')
    archive=build();destination.mkdir(parents=True)
    tree=destination/'smart-travel-planner';tree.mkdir()
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            relative=Path(name.split('/',1)[1]);target=tree/relative
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
    version=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))['version']
    repo=repository or 'YOUR_GITHUB_OWNER/YOUR_REPOSITORY'
    text=f'''# GitHub installation template

Repository status: {'EXPLICIT_MAINTAINER_TARGET' if repository else 'UNCONFIGURED — replace placeholders before publishing'}

Upload the CONTENTS of smart-travel-planner/ to the repository root after review.
Tag v{version}, attach {archive.name} and {archive.name}.sha256.
No repository, tag, upload or public release has been created by this script.

```sh
claude plugin marketplace add {repo}#v{version}
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin list
```

The command above is {'an explicit target template; publication is still required' if repository else 'a non-runnable placeholder template, not an existing install source'}.
'''
    (destination/'INSTALL-COMMANDS.md').write_text(text,encoding='utf-8')
    result={'github_ready_directory':str(tree),'archive':str(archive),'checksum':str(archive)+'.sha256',
            'repository':repository,'publication_status':'NOT_PUBLISHED','upload_performed':False}
    (destination/'release-materials.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);p.add_argument('--repository');a=p.parse_args()
    print(json.dumps(prepare(a.output_dir,a.repository),indent=2))
