---
name: after-effects-setup
description: Set up or troubleshoot Bubble After Effects 26+ native scripting without Creative Cloud, UPIA, developer tools or an AE-side installation.
---

# Setup

Call `after_effects_installation_status` and `after_effects_list_sessions`. Windows and AE 26+ only. Installation discovery checks Adobe's default Program Files tree; session discovery reads the actual executable path and PE version, including custom installs.

No host files, panels, registry entries, startup scripts or persistent bridge are installed. Open the intended AE normally and keep exactly one instance running, counting all versions. Ask the user to enable **Allow Scripts to Write Files and Access Network** in AE's scripting preferences if they want to use file replies. This is a host-wide preference; do not silently change it. The plugin does not need network connections, but Adobe combines file and network permission in that setting.

Call `after_effects_project_info` to check connectivity. A timeout does not establish that the preference is disabled: modal dialogs or routing can also prevent a reply. Report the uncertainty and do not retry writes. Do not call older AE versions for testing. No Creative Cloud, UPIA, developer tools or developer mode are required.

Uninstall through Codex. `after_effects_uninstall_bridge` explains that no AE-side component exists; it does not remove Adobe's preferences. Normal request completion cleans owned temporary scripts/results. A killed Codex process may leave a temporary `bubble-ae-request-*` directory; inspect exact ownership/path before any manual cleanup. No user projects are stored there.

Updates use the Git marketplace and the versioned locked launcher. A running server loads its Python modules into memory, so deleting the installed package does not require deleting Adobe files. Native acceptance on AE 26 is currently pending.
