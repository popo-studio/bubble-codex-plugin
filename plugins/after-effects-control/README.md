# Bubble After Effects 0.2.0

Windows **After Effects 26.x** only. A managed Startup JSX bridge automatically registers each running AE instance. No Creative Cloud, UPIA, developer tools, CEP panel, debug mode, manual pairing code, or repeated script-editor paste is required. Native AE 26 acceptance remains pending; tests with a mocked Adobe DOM are not native acceptance.

## First setup

Use `after_effects_installation_status`, then `after_effects_install_bridge` with `confirmed=false` to preview the exact verified executable and Startup file. Explicitly authorized installation writes one user-specific named `.jsx` under that installation’s `Support Files/Scripts/Startup`. Windows may require administrator write permission for Program Files; failures are reported without silent elevation. Default Adobe Program Files installations are discovered; custom installations are not currently enumerated.

Enable **Allow Scripts to Write Files and Access Network** once yourself in AE preferences, then restart AE. The plugin never changes this setting. Subsequent sessions connect automatically. Only local files are used, despite Adobe combining file/network permission in one setting. Startup defers registration through `app.scheduleTask`; render-engine/watch-folder sessions are excluded. The bridge is scoped to the installing Windows profile before defining globals or touching another bridge.

One AE installation is managed per Windows user. Multiple running instances of that installation are supported. To change the managed installation, explicitly uninstall the previous bridge first; other installation configuration is never overwritten.

## Selection and operations

`after_effects_list_sessions(project=...)` lists connected instances and their project names/paths. Duplicate names remain ambiguous; exact paths can narrow selection. Session UUIDs identify bridge instances, not PIDs. Every operation uses an explicit session ID, and disconnected IDs never fall back to another instance.

Read `after_effects_project_info` first, then pass its `project_state` verbatim to subsequent structured tools. Project state is an observed path/revision/root/item fingerprint, not a permanent GUID. The host also checks project reference continuity. Available operations: inspect items/comps/layer IDs, create a composition, import one media file, add text/solid/footage layers, change static transforms/opacity, save an explicit `.aep`, and execute user-authorized JSX. Existing saves require explicit overwrite permission. Locks, keyframes, expressions and separated transform dimensions are preserved by refusing unsupported static edits.

Each instance serially processes its queue across Codex chats. Requests have private per-instance tokens, unique IDs and deadlines. Claimed `.running` files are never replayed after a crash. Timeouts/partial failures require inspection, never automatic write retries. Installation generation changes revoke old loaded code until AE restarts. The application is never launched by the transport.

Inspection fails closed above 10,000 project items or 10,000 inspected layers. Requests are bounded to 1 MiB; responses to 2 million characters/8 MiB. The queue and discovery scans are bounded and prioritize fresh records. Oversized replies after a write do not imply the write was rolled back.

## Update and uninstall

Install/update is protected by an exclusive per-user lock and stages both Startup code and receipt; failed receipt publication rolls the Startup file back. An interrupted operation may leave `installation.lock`; inspect before removing that exact stale lock.

Preview and authorize `after_effects_uninstall_bridge` before removing the Codex plugin. Only an unchanged owned Startup file is deleted. Modified/missing files are preserved, while the receipt is revoked so loaded pumps stop on their next check. An already executing command may finish. Adobe preferences are unchanged.

Recognized owned heartbeat/request/result files are cleaned within bounded scans. Unknown files and not-yet-expired `.running` requests are retained and reported for inspection. Abrupt termination can leave temporary files; do not claim the runtime directory is always empty. Calling uninstall again after expiry can clean recognized leftovers. Dependencies live in uv’s external cache, and host source is loaded into memory when the MCP server starts, allowing package removal while the server remains alive.

## Evidence and sources

The implementation uses Adobe’s shipped `Support Files/Scripts/Startup/About the Startup folder.txt` semantics and scheduled-task API. Current [Adobe Scripts help](https://helpx.adobe.com/after-effects/desktop/automate-in-after-effects/automate-animation/scripts.html) documents scripting preferences. The Adobe-authored [Scripting Guide](https://fendrafx.com/wp-content/uploads/After-Effects-CS6-Scripting-Guide.pdf), pages 6 and 27–28, documents startup globals and `scheduleTask`/`cancelTask`. No unsupported CEP hidden-autostart assumption or UXP 27 API is used.
