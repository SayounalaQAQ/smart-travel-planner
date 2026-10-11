# Codex adapter

V1.0.2 provides root portable `plugin.json`/`mcp.json`, shared skills, `.agents/plugins/marketplace.json`, and compatibility `.codex-plugin/plugin.json` plus `adapters/codex/mcp.json`. OpenAI settings in portable `extensions.com.openai` replace legacy overlay settings; they are not merged. Claude root variables must not be used in portable args.

Catalog `smart-travel-planner-marketplace` points `source.path` to `./` from the repository root, not `.agents/plugins/`. Keep the whole plugin. In supported local Codex clients, open/register the trusted repository, select its source in Plugins Directory, install/enable and start a new conversation. Local stdio MCP still requires host support and permissions.

Official project enablement form where supported:

```toml
[plugins."smart-travel-planner@smart-travel-planner-marketplace"]
enabled = true
```

Merge this entry into existing `.codex/config.toml`; never overwrite other settings. Project config is loaded only for trusted projects. This release does not edit host config. Personal marketplace paths must be relative to that marketplace root; use the official personal-install example, not a developer absolute path.

`installer/validate_distribution.py` and `verify_installation.py` verify structure/protocol, not GUI install, host variable substitution or automatic matching. Those remain NOT_TESTED. Unsupported hosts can explicitly read the full Skill and use its absolute entry for a session; that is not persistent installation.

Update/uninstall with the client's plugin management, preserving other catalog entries and user documents. This is local stdio distribution, not a remotely hosted server or public store listing.

Official reference: [OpenAI plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins).
