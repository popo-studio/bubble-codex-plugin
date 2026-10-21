---
name: premiere-setup
description: Install, update, remove or troubleshoot Bubble Premiere for Windows Premiere 26.x using a signed CEP panel without Creative Cloud or developer tools.
---

Use the Premiere MCP setup tools first. No Creative Cloud, UPIA, developer mode, registry edits, unsigned extensions or script copying. Only Premiere 26.x is targeted; older and future major versions are not validated. This is a candidate pending native host acceptance; never imply mocked tests prove host loading.

1. Call `premiere_installation_status`. Explain supported host, exact extension destination and current status. Unsupported installed versions require user upgrade; do not install/launch old versions.
2. Preview `premiere_install_bridge`. After the user's installation authorization, call with `confirmed=true`. Only bundled signed resources may be installed. Do not override a modified/unknown extension or manufacture ownership receipts.
3. If the panel is absent, ask the user to restart Premiere. Open Window > Extensions > Bubble Premiere. Call `premiere_pairing_code`, then let the user paste the private connection code and click Connect. This is a connection credential, not script code. Do not save or share it. Keep the panel open.
4. List sessions and inspect the chosen active project. Connection is confirmed only by a real returned session and project information. Empty host sessions can create/open a project through the plugin.
5. Updates follow the same preview/authorization sequence. Close the panel before update. Preview uninstall and use `confirmed=true` when authorized. Removing Codex plugin alone does not remove the CEP extension. Do not remove unknown files or Adobe preferences; surface conflicts and backup paths.

Prefer plugin tools over computer use for project actions. Never silently substitute UI automation or claim completion on an unconnected host. Pending/timeout actions may have run; inspect before another mutation.
