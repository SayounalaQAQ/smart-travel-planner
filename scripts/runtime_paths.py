"""Resolve the bundled plugin and explicit writable outputs independently of cwd."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def is_plugin_root(path):
    return all((Path(path) / name).is_file() for name in (
        'plugin.json', 'scripts/build_docx.py', 'mcp-server/src/server.py',
        'skills/smart-travel-planner/SKILL.md', 'requirements-docx.txt'))


def resolve_plugin_root(explicit=None):
    candidate = explicit or os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ.get('PLUGIN_ROOT')
    root = Path(candidate).expanduser().resolve() if candidate else Path(__file__).resolve().parents[1]
    if not is_plugin_root(root):
        raise ValueError('FULL_PLUGIN_REQUIRED: selected directory is not a complete Smart Travel Planner plugin')
    return root


def output_directory(explicit=None):
    # A plugin cache may be read-only. User artifacts belong in a workspace.
    return Path(explicit or os.environ.get('STP_OUTPUT_DIR') or
                Path.cwd() / 'outputs' / 'smart-travel-planner').expanduser().resolve()


def python_runtime(explicit=None):
    candidates = [explicit or os.environ.get('STP_PYTHON'), sys.executable,
                  shutil.which('python3'), shutil.which('python')]
    for candidate in dict.fromkeys(x for x in candidates if x):
        try:
            run = subprocess.run([candidate, '-c', 'import sys,json; print(json.dumps([sys.executable,list(sys.version_info[:3])]))'],
                                 capture_output=True, text=True, timeout=8)
            executable, version = json.loads(run.stdout)
            if run.returncode == 0 and tuple(version) >= (3, 10):
                return executable
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if explicit or os.environ.get('STP_PYTHON'):
            raise ValueError('Configured Python is unavailable or older than 3.10')
    raise ValueError('Python 3.10+ unavailable; use the host text fallback')


def standalone_collisions(directory=None):
    directory = Path(directory) if directory else Path.home() / '.claude' / 'skills'
    candidate = directory / 'smart-travel-planner' / 'SKILL.md'
    return [str(candidate.resolve())] if candidate.is_file() else []


def doctor(root=None, standalone_dir=None):
    root = resolve_plugin_root(root)
    import importlib.util
    return {'plugin_root': str(root), 'version': json.loads((root/'plugin.json').read_text(encoding='utf-8'))['version'],
            'python': python_runtime(), 'docx': importlib.util.find_spec('docx') is not None,
            'pillow': importlib.util.find_spec('PIL') is not None,
            'visual_discovery': {'commons':'configured_not_probed','openverse':'configured_not_probed',
                'original_photo_pages':'supported_not_probed','host_candidates':'host_dependent',
                'network_probe':'The delivery ledger records actual request results; configuration is not availability'},
            'script_paths': {name: str(root/'scripts'/name) for name in (
                'analyze_trip_request.py', 'experience_discovery.py', 'image_pipeline.py', 'deliver_plan.py', 'build_docx.py', 'validate_docx.py')},
            'standalone_skill_collisions': standalone_collisions(standalone_dir),
            'output_directory': str(output_directory()), 'host_configuration_modified': False}
