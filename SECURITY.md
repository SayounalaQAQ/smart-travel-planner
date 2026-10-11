# Security and privacy

## Trust boundary

Only install from an owner/repository you trust, at a fixed release/tag or reviewed commit. Repository text, pages and search results are untrusted data, not permission to execute code or access credentials. Verify the release SHA256 before execution. A checksum establishes byte integrity, not publisher identity or an independent signature. No signed releases are provided yet.

Installation requires host permission for downloads, dependencies, scripts and enabling local MCP. This project does not register servers, edit host settings, run lifecycle hooks, or install dependencies silently. `prepare_plugin.py --configure-runtime` edits only the explicitly selected plugin copy; do not redistribute that machine-specific copy. Dependencies are version pinned but not wheel-hash locked. Review and use an approved package index.

## Runtime

Travel MCP has no arbitrary shell, browser automation, system mutation, credential reading or booking tools. Its image write is explicit and constrained to the selected output directory. Network requests enforce public HTTP(S), DNS/private-address rejection, redirects, timeouts and size bounds. Images require trusted metadata, allowed license, decode and size checks. Never disable TLS or copy unknown-license images to achieve a success label.

Agent decisions are planning recommendations only. Never pay, reserve, sign agreements or submit personal data without a separate explicit user request and a supported authorized tool.

## Data handling

Plans, screenshots, booking details, generated Word, logs and downloaded photos stay in the user-selected workspace. Do not upload them to GitHub or include them in release assets. Do not commit `.env`, caches or machine-specific MCP commands. Only the declared CC0 regression image is included with provenance; other test/acceptance photos are excluded. Provider requests disclose query text/place/date to the named external service; review those services before including sensitive data.

## Reporting

The project repository is https://github.com/SayounalaQAQ/smart-travel-planner. Use GitHub private vulnerability reporting only if the maintainer enables it; otherwise obtain a private maintainer contact before sending reproduction details. No separate security email is advertised. Do not publish API keys, personal itineraries or exploit-sensitive information in a public issue. Stop compromised-source installation and preserve a minimal sanitized report.
