# Bubble Premiere Pro

Premiere Pro **25.6+** UXP integration for Codex. The user's detected Premiere
2021 / 15.0 cannot load UXP; this package intentionally targets the newer API.
It does not enable CEP debugging or install an old bridge.

## Supported operations

Ten MCP tools: installation status, install/update, uninstall, private pairing
code, session/project selection, project/sequence information, offline-media
inspection, import media into the root bin, relink one item, and save the chosen
project. No arbitrary JavaScript/eval, ExtendScript, QE, timeline editing or
render/export API is exposed in this release.

The media audit scans at most 1000 project bin items, marks host errors
unverified, and surfaces truncation. It is not a complete dependency/sequence or
effects audit. Import/relink changes remain unsaved; relink is not undoable in
Adobe. Save is a separate explicit action.

## Installation and removal

1. Install this Codex plugin and run its setup skill.
2. Check a supported Premiere version and Adobe Creative Cloud/UPIA.
3. Preview the bundled candidate CCX package. Its ZIP layout follows the Adobe
   packaging format; it has not yet been validated by UDT or a native Adobe
   installation. If needed, package `uxp/manifest.json` with UXP Developer Tool
   and pass the resulting absolute `.ccx` path as `package_path`.
4. Approve the returned install plan; the tool validates exact release contents
   before invoking Adobe's official UPIA `/install`. Adobe may require approval.
5. Open the Bubble Premiere Pro panel. Request a pairing code in Codex and paste
   it in the panel's connection field; click Connect. No script copying.

Updates use the same Adobe plugin ID and validate the new release's CCX.
Uninstall previews first and uses UPIA only after exact installed identity is
verified. Unknown UPIA output remains unknown; use Creative Cloud **Manage
Plugins** in that case. We do not edit Adobe's private plugin store. Codex plugin
removal and Adobe panel removal are separate. Close/disconnect the panel to stop
the connection without closing projects. No Adobe profile files or registry
debug switches are written by this integration.

## Multiple instances and lifecycle

Each open, paired panel has an opaque session UUID. Its active project is shown
with name/path/GUID; all other open projects are **not** advertised. Choose the
correct session and project ID, or activate the intended project in Premiere and
list again. Duplicate names remain ambiguous. A native PID is not fabricated.
Every host action checks the project identity and deadline before executing.

The broker listens on a random `127.0.0.1` port with a private token, within the
current MCP process. Panel credentials remain in memory. Restarting Codex/MCP
requires re-pairing. A panel belongs to one chat at a time. Closing the panel
disconnects; no dormant software autostart is installed. Requests/results are
bounded to 1 MiB, queues/HTTP workers to 32. Timed-out commands are never replayed;
an already-started operation may finish and require state inspection.

## Validation limits

Tests cover real loopback authentication, app/session isolation, deadlines,
at-most-once delivery, bounded requests, lifecycle, mocked Adobe UPIA, and public
DOM behavior under a Node mock. These do not constitute a real Premiere 25.6+
UXP load test. This machine has Premiere 15.0, so current host loading, UXP
localhost permission, official CCX packaging and native operations remain for
acceptance on a supported installation.

Official references:

- [UXP Project API](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/project)
- [ClipProjectItem API](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/clipprojectitem)
- [FolderItem API](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/folderitem)
- [UXP networking](https://developer.adobe.com/uxp/guides/how-to/recipes/network/)
- [Official packaging](https://developer.adobe.com/uxp/guides/how-to/distribution/package/)
- [Official installation](https://developer.adobe.com/uxp/guides/how-to/distribution/install/)
