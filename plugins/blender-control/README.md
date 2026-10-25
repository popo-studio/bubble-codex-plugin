# Bubble Blender 0.1.0

Local Blender control through an authenticated loopback bridge. Targets Blender **4.5 LTS and 5.2 LTS**, using public data APIs available since 4.5. Native acceptance was run on installed **4.5.3 LTS**; 5.2 is not locally validated. Versions below4.5 are rejected. Other newer releases are not promised compatible; unsupported API/engine errors must be inspected, never silently worked around.

Codex requires `uv` and independent Python3.10+. The software bridge uses Blender's bundled Python and no third-party packages. Locked MCP1.x and certifi>=2026.10.19 stay outside Blender. The versioned launcher creates its environment outside the removable plugin package and leaves its working directory before execution.

## Installation

Use `blender_installation_status` to preview an exact **user scripts directory**, obtainable inside Blender with `bpy.utils.user_resource('SCRIPTS')`. Standard Windows path: `%APPDATA%/Blender Foundation/Blender/<version>/scripts`. Existing supported profiles are listed; multiple profiles require selection. If none exists, preview defaults to5.2; choose the actual installed version before confirming. Custom `BLENDER_USER_SCRIPTS` paths must be explicitly selected. The installer does not change Blender's preferences, enable add-ons, install software, or modify environment variables.

After authorization, `blender_install_bridge(confirmed=true)` writes its own `startup/bubble_blender.py` and `modules/bubble_blender_runtime/` payload with a hash receipt. Save work and restart Blender. The startup module defers initialization; a persistent `bpy.app.timers` callback executes queued operations on the main thread. Normal GUI sessions connect automatically, including after opening another file. Background Blender skips automatic bridge startup. Factory-startup mode ignores user scripts by Blender design. An optional returned snippet is only for users who prefer connecting without restarting.

Updates/uninstall preserve modified/unknown files and refuse conflicts. A per-profile lock serializes installation changes and ordinary IO failures roll back. An interrupted lock must be inspected before manual removal. `blender_uninstall_bridge` defaults to preview and removes only unchanged owned files after authorization. Restart Blender to stop already loaded code; removing the Codex plugin alone does not remove software-side startup files. Unrelated files and generated directories remain. A crash can leave stale session records; they never authorize another process without that process's token.

## Tools and boundaries

21 tools cover setup, exact instance/file selection, scene state, asset inspection, object listing/create/edit/selection, materials, cameras, lights, timeline, render settings and authorized Python. Multiple instances have independent random ports/tokens; matching uses exact filenames/stems/full paths. Ambiguous or unavailable results require user choice. Explicit PID and fresh structural snapshot are required for changes. The snapshot includes a random per-start bridge session nonce, file/scene/dirty state object session identities and collection identities/memberships, **not every property revision**: read targets immediately before editing and do not interleave user edits.

- Create cubes/custom meshes/empties/cameras/point, sun and area lights. Names are limited to63 UTF-8 bytes to prevent Blender silently truncating them. Mesh input is bounded; no selection-dependent operators.
- Transform uses local coordinates and Euler radians; Euler edits refuse quaternion/axis-angle rotation modes without switching them; locks, constraints and animation refuse static writes. Duplicate copies object data. Deletion requires explicit `confirm_delete=true` and user intent.
- Collection listing/create/rename/link/unlink stays in the current scene and rejects linked/overridden/shared collections. Link a destination before unlinking the last source; no object deletion. Empty name identifies scene root. Listing is capped at1000 collections/10000 memberships.
- Object parenting/detaching preserves world matrix, including nonuniform parent transforms, and rejects cycles, singular parents, shared-scene/locked/constrained/animated children and bone/vertex parenting.
- Material get/create/set/assign supports basic non-node viewport/surface diffuse RGBA, roughness and metallic. Node graphs require authorized Python; assignments reject shared object data.
- Camera lens/clipping and scene activation; light energy/color. Shared/linked/driven data is protected.
- Timeline changes nonnegative frame ranges/current frame/fps (current frame may be negative) without retiming keys. Render settings expose resolution (at least4px)/percentage/engine; **no tool automatically renders or changes output destinations**.
- New/open/save `.blend` guards dirty replacement and overwrite. Opening disables embedded Python and does not load file UI; installed application callbacks remain possible.
- Assets: image/movie/sound/library paths, packed/missing states. Sequence/UDIM completeness, caches/fonts and compositor outputs are unverified.

The bridge binds127.0.0.1 only. Private registry directory is restricted to the current user and SYSTEM on Windows (0700 elsewhere). Requests/responses are bounded to1MiB; captured script output128KiB. Mainthread queue64, timeout<=120s. Queued expired commands are cancelled; executing work cannot be undone by transport timeout. No automatic retry/replay or fallback to a different instance. Authorized Python has full user privileges, including filesystem/network access.

## Validation and sources

`uv run --locked --project plugins/blender-control --python 3.13 python -m unittest discover -s plugins/blender-control/tests` runs isolated ownership/rollback/selection/token/deadline tests. `tests/stdio_smoke.py` exercises all21MCP tools against a fake host. `tests/native_smoke.py` runs real bpy operations in Blender background with factory settings and isolated paths; `tests/native_gui_acceptance.py` owns two hidden GUI processes and isolated profiles for automatic startup/multi-instance checks. Never run native tests against existing user sessions. Native evidence is 4.5.3 only.

Official references: [4.5 timers](https://docs.blender.org/api/4.5/bpy.app.timers.html), [startup module loader source](https://github.com/blender/blender/blob/blender-v4.5-release/scripts/modules/bpy/utils/__init__.py), [Object API](https://docs.blender.org/api/4.5/bpy.types.Object.html), [file operators](https://docs.blender.org/api/4.5/bpy.ops.wm.html), and [current releases](https://www.blender.org/releases/). Icon attribution is in assets/SOURCE.md.

Version0.2.0 updates the software-side bridge payload as well as the Codex tools. Update the owned bridge through setup; an already running0.1.0 bridge must be restarted/reloaded. New APIs: [Collections](https://docs.blender.org/api/4.5/bpy.types.Collection.html), [Object matrix/parent](https://docs.blender.org/api/4.5/bpy.types.Object.html).
