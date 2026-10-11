#!/usr/bin/env python3
"""Start only this plugin's bundled MCP; log errors on stderr, keep stdout JSON-RPC."""
import os
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
try:
    from runtime_paths import python_runtime, resolve_plugin_root
    root=resolve_plugin_root(root)
    executable=python_runtime()
    command=[executable,str(root/'mcp-server/src/server.py')]
    # Windows execv does not reliably retain inherited stdio until its child exits.
    # Keep the launcher alive so the host's JSON-RPC pipes remain connected.
    if os.name=='nt':raise SystemExit(subprocess.call(command))
    os.execv(executable,command)
except (OSError,ValueError) as exc:
    print(str(exc),file=sys.stderr);raise SystemExit(2)
