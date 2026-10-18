---
name: plugin-maintenance
description: Guide safe updates, repairs and complete removal of Bubble plugins using supported Codex and owning-plugin tools.
---

Get `doctor_repair_guidance` with the exact plugin and repair/update/uninstall action. It returns instructions, not executed changes. Use diagnostics first so the requested action is concrete.

Codex plugin and software bridge installations are separate. Use Codex's supported plugin/marketplace tools or UI for refresh, reinstall and uninstall. Discover the actual registered marketplace; do not assume every user named it bubble-plugins. Do not directly edit Codex cache/config or delete shared uv environments. A Git push or cache refresh does not reload an already running MCP process.

For DCC bridges, keep the owning plugin installed until its `*_uninstall_bridge` finishes. Obtain the exact software profile/version or project, call its installation status and preview with `confirmed=false`, show changed paths and preserve ownership conflicts. Then use `confirmed=true` only when the user has authorized those concrete changes. Existing explicit authorization remains valid; do not repeatedly ask for the same approval.

After installation/update/removal ask the user to save work and restart/refresh the software as appropriate. Do not close Maya/Nuke/etc automatically. Rediscover the explicit instance afterwards. If the owning tools are missing, diagnose their Codex load and temporarily reinstall from the same trusted source using supported host tools.

Deadline, Sequence Check, Asset Package and Plugin Doctor have no software-side bridge. Removing their Codex plugins does not remove render jobs, delivery folders, reports or uv's shared cache. Doctor is a guided maintenance entrypoint, not a background updater or automatic process killer.
