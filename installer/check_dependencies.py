#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; deps=json.loads((root/'config/dependencies.json').read_text(encoding='utf-8'))
result={'python':sys.version.split()[0],'python_executable':sys.executable,'plugin_root':str(root),'python_ok':sys.version_info>=(3,10),'optional_docx_available':False,'optional_image_processing_available':False,'mcp_dependency_count':0,
        'standard_generator_present':(root/'scripts/build_docx.py').is_file(),'image_pipeline_present':(root/'scripts/image_pipeline.py').is_file()}
try:
 import docx; result['optional_docx_available']=True; result['python_docx_version']=docx.__version__
except ImportError: pass
try:
 import PIL; result['optional_image_processing_available']=True; result['pillow_version']=PIL.__version__
except ImportError: pass
print(json.dumps(result,indent=2)); sys.exit(0 if result['python_ok'] else 1)
