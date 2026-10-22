---
name: after-effects-setup
description: Install, update, remove or troubleshoot the automatically connected AE26.x Startup bridge without Creative Cloud or developer tools.
---

# Setup

Use `after_effects_installation_status`, then preview `after_effects_install_bridge` with the exact verified executable. With explicit installation authorization, set `confirmed=true`. The user-specific Startup JSX file lives in `Support Files/Scripts/Startup`; Program Files may require Windows administrator write permission. Do not change permissions broadly or install Creative Cloud, UPIA, developer tools, CEP debug mode, or fallback transports.

Ask the user to enable **Allow Scripts to Write Files and Access Network** once manually if necessary and restart AE after installing/updating. Never change the preference automatically. Normal later connections require no panel, connection code, or script-editor paste. Native AE26 validation is pending; do not conflate mocks/MCP startup with native acceptance.

Only AE26.x and one managed installation per Windows user are supported. Multiple instances of that installation register independently. `after_effects_list_sessions` returns project names/paths and per-instance UUIDs. Ask the user to choose if name/path matching remains ambiguous. Do not close instances or guess the first.

Uninstall the host bridge using preview then authorized `after_effects_uninstall_bridge` before removing the Codex plugin. Modified Startup files are preserved and the receipt is revoked. Loaded pumps stop on their next check; already running commands may finish. Bounded cleanup preserves unknown files and live running requests. Inspect reported retained files; never recursively delete an arbitrary Adobe or runtime directory. Adobe preferences remain unchanged.
