# Bubble Premiere Pro 0.5.0

Current Codex package: **0.5.0**. Software-side signed bridge: **0.5.0**; update the bridge and restart Premiere once to load these new commands.
Candidate integration for **Windows Premiere Pro 26.x only**, using a signed CEP 12 background bridge and local MCP broker. Older versions and untested future major versions are rejected. No Creative Cloud, UPIA, UXP Developer Tool, debugger setting or script pasting is required. This differs from Photoshop COM: Premiere needs a small signed background extension installed in its per-user extensions folder.

## Setup and lifecycle

Run the setup skill, inspect the installation preview, then authorize installation. The signed payload is installed under `%APPDATA%/Adobe/CEP/extensions/com.popostudio.bubble.premiere`, with an adjacent ownership receipt. **Restart Premiere once after first installation or any software-side bridge update.** The invisible CEP background extension starts on Premiere's documented application activation event. No panel opening, connection code, or script copying is needed during normal use.

Calling `premiere_list_sessions` starts this chat's broker and automatic discovery. Each broker publishes a random UUID, random loopback port and credential in `%LOCALAPPDATA%/Bubble/Codex/premiere/discovery`. Before any credential is written, a protected Windows DACL restricts access to the current user and SYSTEM. Records refresh every 3 seconds and expire after 12 seconds; credentials are never returned by tools or logged. This is same-user local automation, not a network service.

Every running Premiere background instance connects independently to all live local Codex brokers. Each connection receives a session UUID; list project names/paths and choose explicitly when multiple matches exist. Only the active project is advertised. All brokers share one execution queue inside each Premiere instance, and queued commands recheck project, installation and deadline before executing. Reconnection creates a new session; it never replays an earlier write or redirects a disconnected session ID.

Installation authorization includes automatic connections to current-user local Codex chats. Only a fully matching managed 0.5.0 installation advertises. Updates and removal protect modified/unknown files. Uninstall removes the managed receipt, extension and owned discovery records; already loaded background code notices revocation and disconnects within a few seconds. An operation already executing may finish. Restart Premiere to unload cached code completely. Codex plugin removal and Premiere extension removal remain separate. No Adobe preferences, debug flags, or projects are changed by setup.

## Tools

The original core tools cover installation status/install/uninstall, automatic connection status, session selection, project info, media inspection, import, relink, save, timeline inspection, sequence creation from chosen source clips, and new/open project from an empty application.

- Create a new `.prproj` only at a nonexistent local absolute path, with no projects open. Open an existing `.prproj` only when no projects are open; Adobe conversion/offline warnings remain enabled. Neither action closes or discards work.
- Create a sequence from explicit online source clip IDs; settings follow source media. No implicit project save.
- Import media into the root bin; relink one explicit item with Adobe compatibility checks. Relinking is not undoable; inspect state after an uncertain result.
- Inspect up to 1000 project items or timeline clips. Truncation and unreadable media fields remain visible. This is not a complete effect, transition or dependency audit.
- Save only to the selected project's existing path. No arbitrary JSX, QE, automatic retries, render/export, effects, transition editing, or automatic project closing.

## Verification status

The signed package is produced and verified using Adobe's standalone ZXPSignCmd. Unit tests and real MCP stdio/HTTP tests use a simulated Adobe DOM; **native Premiere 26 installation, background loading, API behavior, connection and uninstall remain unverified**, pending user installation of the latest host. The local Premiere 2021 is intentionally not used as acceptance evidence.

## Release signing (maintainer only)

`tools/build_signed_release.py --signer <absolute ZXPSignCmd.exe> --certificate <external .p12> --password-env BUBBLE_CEP_SIGNING_PASSWORD` builds `adobe/com.popostudio.bubble.premiere.zxp`, extracted `adobe/signed/`, and `adobe/release.json`. The password and private key are never included. The candidate is self-signed without a timestamp, so certificate expiry applies; re-sign before expiry. Any CEP source change requires rebuilding the signed payload.

Sources: [Adobe CEP12 integration/extension folders](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md), [Adobe signing guide](https://github.com/Adobe-CEP/Getting-Started-guides/blob/master/Package%20Distribute%20Install/readme.md), [Adobe Premiere scripting example](https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/jsx/PPRO/Premiere.jsx).

## 0.4 workflow additions

23 tools include bin creation, project-item and sequence renaming, sequence settings inspection, exact-tick playhead positioning, sequence in/out range editing, and sequence-marker listing/creation/update by GUID. Renaming an item does not rename its disk file. Sequence ranges do not trim clips. Marker updates preserve the start time; they can change name, comments, end time and color. All operations require an explicit session and the observed project identity.

This release does not expose undocumented QE editing, clip trimming or arbitrary effect manipulation. The public ExtendScript signatures are evidenced by Adobe's [PProPanel sample](https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/jsx/PPRO/Premiere.jsx). Automated host-DOM tests are not Premiere 26 native acceptance. An unchanged managed 0.3 installation can be updated through the installer; modified files are preserved and reported. Restart Premiere after updating the signed bridge.

## Runtime security patch 0.4.1

The Codex package updates its locked Python dependencies. Software-side bridge code and its version remain unchanged; existing owned bridge installations do not require reinstalling for this dependency-only update. Reload the Codex plugin to start the patched runtime.

## 0.5 project organization additions

27 tools now include `premiere_move_item`, `premiere_duplicate_sequence`, `premiere_track_state` and `premiere_delete_marker`. Bin moves preserve source files and reject descendant cycles. Sequence duplication verifies a new sequence ID and requires a unique name. Track mute changes require the exact fresh returned ID/name/index/mute fingerprint. Marker deletion requires its exact GUID and fresh observed name/comments/start/end. No QE or arbitrary scripts are used; all writes retain project/session/deadline guards and must never be replayed automatically.

Update the managed signed bridge to **0.5.0**, then restart Premiere once. Unchanged owned older bridges can be updated; modified/unknown files remain protected. New commands have DOM contract coverage; Premiere 26 native loading/API acceptance remains pending. Public mute usage is present in Adobe's PProPanel sample. Additional signatures are cross-checked with the community-maintained Premiere scripting guide; it is not Adobe-hosted and does not substitute for native verification.
