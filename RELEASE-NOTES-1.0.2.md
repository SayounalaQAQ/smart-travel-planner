# Smart Travel Planner v1.0.2 Release Notes

Release: **v1.0.2**. Repository: [SayounalaQAQ/smart-travel-planner](https://github.com/SayounalaQAQ/smart-travel-planner). Full plugin source and versioned distribution; actual host installation remains **NOT_TESTED**.

## Changes

Complete plugin distribution with Claude user-scope Marketplace instructions, portable Codex entry and capability-aware cloud Agent installation. Fixed Word daily headings, unresolved route presentation and repeated engineering status tables; preserved photos, attribution, uncertainty and currency. Existing travel planning engines are retained.

## Assets

- `Smart-Travel-Planner-1.0.2.zip`: full plugin, scripts, documentation and regression contracts.
- `Smart-Travel-Planner-1.0.2.zip.sha256`: exact artifact checksum.
- Beginner, advanced and AI-assisted guides included at the package root.

No standalone Skill-only ZIP. No user itineraries, generated manuals, credentials, acceptance logs or unlicensed images in the asset. Example manuals and local acceptance evidence are separate deliverables and are **not** publication assets by default.

## Maintainer publication checklist

1. Inspect the generated GitHub-ready directory, licenses, excluded data and full regression log. Supply your actual owner/repository to `scripts/prepare_github_release.py --repository owner/repo --output-dir <new-directory>` to generate exact install commands; no upload occurs.
2. Create/select the authorized repository yourself. Upload the contents of the GitHub-ready directory at the repository root; do not upload the unfiltered development workspace or include a version wrapper above `.claude-plugin/marketplace.json`.
3. Confirm `plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and MCP all use 1.0.2; validate marketplace source `./`. Run regressions and clean-package checks.
4. Commit the reviewed tree, create `v1.0.2` pointing to that commit, create a Release, attach the ZIP and matching checksum. Do not execute these GitHub mutations without owner authorization.
5. Public guides use SayounalaQAQ/smart-travel-planner. Regenerate/retest the package after any edit and attach the resulting checksum. Never advertise an old checksum for new bytes.
6. Perform Claude user-scope installation and normal restart; record actual installed/enabled status. Separately test Codex and an authorized cloud Agent. Until performed, host install status remains NOT_TESTED. Structural configuration PASS is distinct.

## Known limits

Not a standalone application or hosted backend. Agent research/execution/file permissions are required. No verified structured transit timetable provider or guaranteed target-date inventory. Unknown costs remain unknown. Actual host installations and per-page Word visual inspection are not established by manifests, unit tests or `--plugin-dir`.

Local engineering evidence is reported separately in `V1.0.2-RELEASE-ACCEPTANCE.md` delivered with this development task. Public Release verification should link a sanitized maintainer result after publication; no personal acceptance input is bundled.
