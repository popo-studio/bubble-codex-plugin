---
name: premiere-setup
description: Install, update, uninstall, pair or troubleshoot the Bubble Premiere Pro UXP panel for Premiere 25.6 and newer.
---

# Bubble Premiere Pro setup

Use `premiere_installation_status` first. This integration targets Premiere Pro
25.6+ UXP, not Premiere 2021/15.x or CEP. Explain version mismatch instead of
changing Adobe settings or enabling old debug flags.

Use `premiere_install_bridge(confirmed=false)` to preview exact package and Adobe
installer changes. Once the user authorizes installation or an update, call with
`confirmed=true`. Adobe may require its own approval. The bundled candidate CCX
is not yet native-host validated; a UDT-packaged release-matching CCX can be
passed as `package_path` if needed. Never pretend source files installed a panel. Use only the
returned official installation instructions; do not manually copy into Adobe's
private plugin cache.

Open the Bubble Premiere Pro panel in the supported host. Call
`premiere_pairing_code` only for a requested connection; show its private code to
this user, never store it in source/logs or send it elsewhere. The user pastes the
code into the panel and clicks Connect, with no Script Editor code. Keep the
panel open. Codes and connections belong to this MCP process; restarting Codex
requires re-pairing. A panel connects to one chat at a time.

Call `premiere_list_sessions` to confirm the actual connection. Installation
success does not prove live host operation. Session UUIDs identify panels; no
host PID is inferred. Only the active project in each panel is advertised.

For removal, preview `premiere_uninstall_bridge(false)` then apply authorized
removal. Adobe host-plugin removal and Codex-plugin removal are separate.
Disconnect/close the panel immediately; do not close projects or Adobe itself.
Do not alter unrelated files. Updates keep the same
Adobe ID and require reconnection; never retry uncertain writes.
