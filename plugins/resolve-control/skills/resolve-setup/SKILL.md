---
name: resolve-setup
description: Set up or troubleshoot Bubble DaVinci Resolve using the official local external scripting SDK, without installing a Resolve-side bridge.
---

Use `resolve_setup_status` first. This Windows release targets **DaVinci Resolve Studio 21+** and 64-bit Python 3.10/3.11. Free edition external scripting is unsupported. Check the installed application's Help > Documentation > Developer > Scripting README for version-specific requirements.

No code copy, panel, custom startup script or Resolve-side installation is needed. The native SDK ships with Resolve. The user must enable Preferences > System > General > External scripting using: **Local** and restart if the application requests it. Explain this prerequisite; do not claim automatic connection before it is enabled. Never enable Network scripting, bypass licensing, install another app or rewrite preferences automatically.

Once the user opens Resolve normally, call `resolve_list_sessions`. This connects on demand after setup. List processes and project names. Keep the returned session_id for subsequent requests. The API has no documented PID routing: if more than one Resolve process exists, explain the limit and ask the user to retain only the intended instance. A selection cannot override this limit. Never close processes for the user or silently choose another after failure.

An SDK module override may be provided through `RESOLVE_SCRIPT_API`, pointing to the installed official Scripting directory; it must be absolute. The DLL is taken from the running process's installation directory. Do not download or substitute third-party SDK binaries. Diagnose missing SDK, missing Studio/local preference and native Python compatibility separately. This release has automated mock/protocol coverage, but no actual Resolve host validation on the author's machine.

`resolve_install_bridge` is status only, not an installer. `resolve_uninstall_bridge` explains zero-install removal; it deletes nothing. To uninstall, remove Bubble Resolve from Codex. To update, refresh/reinstall the Codex plugin and reconnect; native workers are per call, with no persistent software bridge to update. Preserve the vendor SDK and user preferences.
