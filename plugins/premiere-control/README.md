# Bubble Premiere Pro 0.3.0

Candidate integration for **Windows Premiere Pro 26.x only**, using a signed CEP 12 background bridge and local MCP broker. Older versions and untested future major versions are rejected. No Creative Cloud, UPIA, UXP Developer Tool, debugger setting or script pasting is required. This differs from Photoshop COM: Premiere needs a small signed background extension installed in its per-user extensions folder.

## Setup and lifecycle

Run the setup skill, inspect the installation preview, then authorize installation. The signed payload is installed under `%APPDATA%/Adobe/CEP/extensions/com.popostudio.bubble.premiere`, with an adjacent ownership receipt. **Restart Premiere once after first installation or updating from 0.2.0.** The invisible CEP background extension starts on Premiere's documented application activation event. No panel opening, connection code, or script copying is needed during normal use.

Calling `premiere_list_sessions` starts this chat's broker and automatic discovery. Each broker publishes a random UUID, random loopback port and credential in `%LOCALAPPDATA%/Bubble/Codex/premiere/discovery`. Before any credential is written, a protected Windows DACL restricts access to the current user and SYSTEM. Records refresh every 3 seconds and expire after 12 seconds; credentials are never returned by tools or logged. This is same-user local automation, not a network service.

Every running Premiere background instance connects independently to all live local Codex brokers. Each connection receives a session UUID; list project names/paths and choose explicitly when multiple matches exist. Only the active project is advertised. All brokers share one execution queue inside each Premiere instance, and queued commands recheck project, installation and deadline before executing. Reconnection creates a new session; it never replays an earlier write or redirects a disconnected session ID.

Installation authorization includes automatic connections to current-user local Codex chats. Only a fully matching managed 0.3.0 installation advertises. Updates and removal protect modified/unknown files. Uninstall removes the managed receipt, extension and owned discovery records; already loaded background code notices revocation and disconnects within a few seconds. An operation already executing may finish. Restart Premiere to unload cached code completely. Codex plugin removal and Premiere extension removal remain separate. No Adobe preferences, debug flags, or projects are changed by setup.

## Tools

14 tools cover installation status/install/uninstall, automatic connection status, session selection, project info, media inspection, import, relink, save, timeline inspection, sequence creation from chosen source clips, and new/open project from an empty application.

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
