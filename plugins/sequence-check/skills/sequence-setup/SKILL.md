---
name: sequence-setup
description: Check the Bubble Sequence Check runtime and explain inspection limits before its first use or when tools fail to load.
---

Call sequence_status to verify actual decoder availability. The deployed launcher uses uv and an isolated Python 3.13 runtime; locked dependencies are provisioned in uv's external script cache. No DCC bridge, startup script, service, or application restart is needed. Do not write package-local virtual environments. If tools are missing, inspect the installed plugin's MCP startup diagnostic; never claim availability based only on its skill being visible.

Explain that scans are read-only and require an explicit absolute directory, with optional filename glob. Use sequence_discover to identify groups before expensive inspection. Do not scan whole disks. A no-match, unsupported format, limit, or decoder error is not a successful quality check.

An explicitly requested JSON/CSV report can be previewed and written using sequence_write_report to a new absolute path. It never overwrites an existing file or changes source images. Report files remain after plugin uninstall.

Updates use the marketplace's normal refresh/reinstall flow; remove the plugin through Codex to uninstall. No application-side files are installed; uv's shared dependency cache may remain and must not be indiscriminately deleted.
