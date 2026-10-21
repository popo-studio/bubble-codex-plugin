---
name: premiere-setup
description: Install, update, remove or troubleshoot Bubble Premiere for Windows Premiere 26.x using an automatic signed CEP background bridge without Creative Cloud or developer tools.
---

Use the Premiere MCP setup tools first. No Creative Cloud, UPIA, developer mode, registry edits, unsigned extensions or script copying. Only Premiere 26.x is targeted; older and future major versions are not validated. This is a candidate pending native host acceptance; never imply mocked tests prove host loading.

1. Call `premiere_installation_status`. Explain supported host, exact destination, and that installation authorizes automatic same-user local Codex connections. Unsupported versions require user upgrade; never install/launch old versions.
2. Preview `premiere_install_bridge`; after installation authorization use `confirmed=true`. Only bundled signed resources may be installed. Do not overwrite modified/unknown extensions or manufacture ownership receipts.
3. Ask the user to restart Premiere once after first installation/update. The invisible signed background bridge starts automatically. Do not ask the user to open a panel, paste a code, or copy scripts.
4. Call `premiere_list_sessions`; it starts this chat's automatic discovery. If multiple instances/projects match, list names/paths and ask the user to choose; never take the first. `premiere_connection_status` reports setup/discovery without exposing credentials. A real returned session is required to claim connected.
5. Preview uninstall, then use `confirmed=true` when authorized. Removal revokes the receipt and disconnects the background bridge shortly; already executing operations may finish. Restart Premiere to unload cached code. Codex plugin removal alone does not remove the Adobe extension. Preserve unknown files; surface ownership conflicts.

Prefer plugin tools over computer use for project actions. Never silently substitute UI automation or claim completion on an unconnected host. Pending/timeout actions may have run; inspect before another mutation.
