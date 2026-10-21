# Bubble After Effects 0.1.0

Windows After Effects **26+ only**. Native `AfterFX.exe -r` executes JSX in an existing application. No Creative Cloud, UPIA, developer tools, panel or persistent host installation is required. This is a candidate implementation: MCP/unit validation is separate from native AE 26 acceptance, which remains pending.

## Setup and routing

Install the Codex plugin, open AE normally, and enable **Allow Scripts to Write Files and Access Network** yourself in AE scripting preferences. The plugin never changes this host-wide preference. Only local request/response files are used. Leave exactly one AfterFX process running across all versions; the native CLI has no PID selector, so multiple instances are refused instead of guessed.

Session IDs combine PID and creation time; executable/PE version and process identity are verified before and after dispatch. A native random token is established by read-only project inspection. Writes require that token plus project reference continuity and an exact observed project-state snapshot. The snapshot is **not** a permanent unique project GUID. Reference continuity across scripts still needs native acceptance.

There is an unavoidable race if AE exits immediately before `-r`: Adobe may launch a new application process. The new process has no session token and cannot execute a content mutation. A timeout may mean the operation executed without a readable reply. Never retry automatically.

## Tools

`after_effects_installation_status`, `after_effects_list_sessions`, `after_effects_uninstall_bridge`, `after_effects_project_info`, `after_effects_inspect_item`, `after_effects_create_comp`, `after_effects_import_file`, `after_effects_add_layer`, `after_effects_set_transform`, `after_effects_save_project`, `after_effects_execute_script`.

Create comps, import individual media files, add text/solid/footage layers, edit static transforms and opacity, inspect stable IDs, and save to an explicit .aep path. Use the latest returned `project_state` on each call. Transform tools refuse locks, keyframes, expressions, and separated dimensions. Raw authorized JSX is an explicit advanced fallback. Import codecs and formats depend on AE; the tool does not automatically import sequences, scripts or other projects. Saving checks existing paths twice and requires explicit overwrite permission.

Inspection refuses projects above 10,000 items or requests traversing more than 10,000 composition layers; it never reports a truncated project fingerprint as complete. Replies are capped at 2 million characters in AE and 8 MiB on receipt. An oversized reply after a write is an unknown outcome, not permission to repeat the operation.

## Lifecycle

Uninstall the Codex plugin. There are no AE files, services, startup hooks or registrations to remove. Adobe preferences remain unchanged. Owned request directories are cleaned on normal completion; abrupt termination may leave temporary files for later exact-path cleanup. Locked dependencies are in uv's external cache, not the package. All server modules are imported at startup, and the launcher leaves the plugin working directory, allowing package updates/removal while running.

## Sources

Adobe's [Scripts documentation](https://helpx.adobe.com/after-effects/desktop/automate-in-after-effects/automate-animation/scripts.html) documents native `-r` invocation and scripting preferences. The local official AE scripting examples document `Pref_SCRIPTING_FILE_NETWORK_SECURITY`; no UXP-only project GUID or API is assumed for ExtendScript.
