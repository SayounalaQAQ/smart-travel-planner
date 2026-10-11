# Claude Code adapter

Persistent entry: repository-root `.claude-plugin/marketplace.json`, named `smart-travel-planner-marketplace`; plugin `smart-travel-planner` has source `./`. The full root contains `.claude-plugin/plugin.json` version 1.0.2, skills, scripts and `.mcp.json`.

From the verified extracted directory:

```sh
claude plugin marketplace add ./
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin list
```

Restart normally after enabled status is confirmed. `--plugin-dir` is temporary loading, not persistent installation proof. The host substitutes `${CLAUDE_PLUGIN_ROOT}` for MCP args and `${CLAUDE_SKILL_DIR}` in Skill commands. Skill folder is not root; do not install a duplicate standalone Skill.

First use: doctor, dependencies, output permissions and authorized MCP/network probes. Python must be executable by the host. Configure PATH or the explicitly selected plugin copy; do not redistribute absolute local paths. See [beginner](../../README-BEGINNER.md) and [advanced](../../README-ADVANCED.md) guides. Structural configuration PASS; actual user-scope install NOT_TESTED.

Official source: https://code.claude.com/docs/en/plugin-marketplaces
