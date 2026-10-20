---
name: photoshop-setup
description: Preview, install, update, remove or troubleshoot the Photoshop 26.2+ UXP panel through Adobe's official tools with user consent, then pair it with this Codex process.
---

# Set up Bubble Photoshop

1. Call `photoshop_installation_status` and inspect the actual host and Adobe installer availability. Photoshop 2025 version 26.2 or later is required; 2021 version 22 is not supported by this package.
2. Call `photoshop_install_bridge(confirmed=false)` to show the included candidate CCX package path and official Adobe install effects. An optional package_path can select a release-matching CCX produced by Adobe UXP Developer Tool. The included reproducible CCX has not yet been validated in Adobe; do not claim native installation success before checking it. A general question is not consent. If the user already authorized those concrete changes, proceed; otherwise get approval before confirmed=true. Never copy files into Adobe's private plugin directories, edit security settings, silently enable developer mode, or claim a staged CCX is an installed panel.
3. Use official Adobe installation. An exit code alone does not prove the panel loaded. If UPIA is absent, follow the returned Creative Cloud/UXP Developer Tool instructions; do not invent an automatic install fallback. Explain any remaining user interaction.
4. User opens Photoshop's Plugins panel and Bubble Photoshop, then keeps it open. Request `photoshop_pairing`, show its private connection code, and have user paste that code into the panel and click Connect. It is a pairing credential, not script-editor code. Each Codex MCP process owns a separate broker; reconnect explicitly after restart or switching chats.
5. Verify with `photoshop_list_sessions` and `photoshop_scene_info`, distinguishing package staging, Adobe install evidence and a live paired host. List multiple sessions/documents and ask which target to use.

Updates use the same preview/confirmed installer with the new package version. Never terminate Photoshop or discard work to update. User may need to close and reopen the Adobe panel or application.

Uninstall uses `photoshop_uninstall_bridge(confirmed=false)` then confirmed=true after user authorization. The installer delegates removal to Adobe and does not delete Adobe private files or the source package. Never delete unknown files or force past ownership conflicts. Disconnect/close any live panel first; removal from Codex alone does not remove Adobe's panel. Never uninstall other Adobe extensions, even when they share the same installation directory.
