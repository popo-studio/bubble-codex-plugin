# Bubble Asset Package 0.2.0

Local Codex tools for explicit asset dependency delivery. Requires `uv` and Python 3.10+; uses a locked script environment outside the removable plugin cache. No DCC bridge installation or startup changes. Install/update/uninstall through the Bubble marketplace; uninstalling does not remove deliveries.

Tools: `package_status`, `package_preview`, `package_execute`, `package_verify`, `package_compare`.

Supply absolute file paths, or a UTF-8 JSON manifest containing `{"paths": ["D:/project/scene.ma", "D:/project/tex/diffuse.<UDIM>.exr"]}`. Filename-only `<UDIM>`, `####`, `%04d`, `$F4`, `$F` expansion is supported. A project root preserves relative layout under `project/`; external assets use `external/<parent-path-hash>/<filename>`. Preview hashes all sources, reports missing and duplicate inputs and gives a deterministic plan hash. Execution requires explicit authorization of that plan and a new destination outside project/source folders. Existing folders are never overwritten.

Execution rechecks the plan and copies using exclusive creation, then writes `package-manifest.json` and verifies SHA256. Partial errors retain the new partial directory and identify completed files; choose a new destination after inspection. No source deletion or automatic cleanup. Bounds: 10000 files, 100 GiB total, 100000 directory entries per token scan, 8 MiB input/output manifest reads. UNC and Unicode paths are supported if accessible; symlinks, junctions/reparse points, parent traversal, ADS and ambiguous Windows names are rejected.

Scope: only supplied dependencies. Binary scenes are not parsed, paths are not rewritten, no promise of scene portability or all expected frames/tiles. Set package_verify(include_extras=true) to flag unexpected delivery files (bounded to 40000 directory entries, no links/reparse traversal). Default verifies listed files only; empty directories are not checked. The unsigned manifest does not establish authenticity. Source/destination paths must be stable: ordinary changes are detected but this is not a sandbox against malicious concurrent filesystem replacement. Source names/absolute paths are recorded in the local delivery manifest; review before sharing externally.

package_compare reports added/removed/changed files between two exact delivery manifests by relative path, size and SHA256. It does not hash the actual asset bytes: use package_verify separately for each delivery. External source-parent changes appear as added/removed mappings; renames are not inferred. No files are modified.

The icon is original SVG artwork for this repository; no third-party logo assets.

Tests: `python -m unittest discover -s plugins/asset-package/tests -v`; stdio smoke: `python plugins/asset-package/tests/stdio_smoke.py` (MCP SDK required).

## Runtime security patch 0.1.1

The Codex package updates its locked Python dependencies. This does not change external software configuration or existing data. Reload the Codex plugin to start the patched runtime.
