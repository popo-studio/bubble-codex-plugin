---
name: photoshop-setup
description: Set up or troubleshoot Bubble Photoshop using existing Windows COM automation, without Creative Cloud, UPIA, developer tools or a Photoshop-side plugin.
---

# Photoshop setup

Use `photoshop_installation_status`, then `photoshop_list_sessions`. This Windows-only plugin uses Photoshop's existing native COM automation; installing Bubble Photoshop in Codex is sufficient. Do not install Creative Cloud Desktop, UPIA, UXP Developer Tool, a CCX, or a panel. Do not enable developer mode, modify the registry, patch Photoshop, change licensing, create startup scripts, or create a fake bridge installation receipt.

Ask the user to open their installed Photoshop normally if it is not running. Tools never launch Photoshop. Version-specific COM registrations must match the running executable; do not use the unversioned Photoshop.Application alias, which may point to an older release. Tested native target is Photoshop 2025 (26.2.0); other installations need their own acceptance test. Existing native COM support is the prerequisite; unsupported or missing registration is a diagnostic, not permission to change system configuration.

List session IDs, PIDs, versions, executable paths and document names. Retain an explicitly chosen session ID for later operations. A filename may identify a session only when the discovery result is complete and unique. If multiple processes use the same executable, COM cannot safely select a PID: explain this limitation and ask the user to keep only the intended instance open. Never silently close applications or switch to another process.

`photoshop_install_bridge` is a compatibility status call: it installs nothing. `photoshop_uninstall_bridge` removes no Photoshop files because native mode installed none. Uninstall the Codex plugin using Codex's normal removal tool to remove its tools and package. Never remove Adobe's native COM registration. Any separately installed old UXP panel is outside native mode and needs its original removal route; do not claim it was removed.

For updates, update the Codex marketplace/plugin and reload tools. No Photoshop-side bridge update or restart is normally required. A timed-out COM worker may leave Photoshop still executing a request; inspect the state and never automatically retry. Do not kill Photoshop to recover a tool.

After connecting, prefer the Photoshop plugin tools for all supported actions. An empty document list is a normal connected state: create a requested image with `photoshop_create_document` or open a requested file with `photoshop_open_file`. Use `photoshop_activate_document` to switch to the explicitly chosen document before authorized JSX. Do not use computer automation just to create/open/activate a document.
