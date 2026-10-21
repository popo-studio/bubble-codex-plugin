# Bubble Premiere Pro 0.2.0

Candidate integration for **Windows Premiere Pro 26.x only**, using a signed CEP 12 panel and local MCP broker. Older versions and untested future major versions are rejected. No Creative Cloud, UPIA, UXP Developer Tool, debugger setting or script pasting is required. This differs from Photoshop COM: Premiere needs a small signed panel installed in its per-user extensions folder.

## Setup and lifecycle

Run the setup skill, inspect the installation preview, then authorize installation. The bundled signed payload is copied to `%APPDATA%/Adobe/CEP/extensions/com.popostudio.bubble.premiere`; ownership and file hashes are recorded in an adjacent receipt. Restart Premiere if the panel is absent, open **Window > Extensions > Bubble Premiere**, request a private connection code and paste it into the panel. Keep the panel open. Nothing starts invisibly or launches Premiere automatically.

Each Codex server uses a random loopback port and private token. Every connected panel has a separate session UUID; the active project is identified by its document ID, name and path. Multiple matches require selection. Only the active project is advertised; activate another project in Premiere and list again. Connection credentials stay in memory. Closing the panel disconnects; Codex restart requires a new code. Queued requests expire, are delivered at most once and never replayed after uncertain failures.

Install/update validates exact release files and ownership; unknown or modified files block replacement or removal. Close the panel before update/uninstall. Uninstall removes only the managed extension and receipt. Already loaded code stops when the panel closes or Premiere restarts. Codex plugin removal and the Premiere extension removal are separate. No projects, preferences or registry debug flags are removed. Adobe upgrades may remove manually deployed CEP files; inspect setup status before repair.

## Tools

14 tools cover installation status/install/uninstall, pairing, session selection, project info, media inspection, import, relink, save, timeline inspection, sequence creation from chosen source clips, and new/open project from an empty application.

- Create a new `.prproj` only at a nonexistent local absolute path, with no projects open. Open an existing `.prproj` only when no projects are open; Adobe conversion/offline warnings remain enabled. Neither action closes or discards work.
- Create a sequence from explicit online source clip IDs; settings follow source media. No implicit project save.
- Import media into the root bin; relink one explicit item with Adobe compatibility checks. Relinking is not undoable; inspect state after an uncertain result.
- Inspect up to 1000 project items or timeline clips. Truncation and unreadable media fields remain visible. This is not a complete effect, transition or dependency audit.
- Save only to the selected project's existing path. No arbitrary JSX, QE, automatic retries, render/export, effects, transition editing, or automatic project closing.

## Verification status

The signed package is produced and verified using Adobe's standalone ZXPSignCmd. Unit tests and real MCP stdio/HTTP tests use a simulated Adobe DOM; **native Premiere 26 installation, panel load, API behavior, connection and uninstall remain unverified**, pending user installation of the latest host. The local Premiere 2021 is intentionally not used as acceptance evidence.

## Release signing (maintainer only)

`tools/build_signed_release.py --signer <absolute ZXPSignCmd.exe> --certificate <external .p12> --password-env BUBBLE_CEP_SIGNING_PASSWORD` builds `adobe/com.popostudio.bubble.premiere.zxp`, extracted `adobe/signed/`, and `adobe/release.json`. The password and private key are never included. The candidate is self-signed without a timestamp, so certificate expiry applies; re-sign before expiry. Any CEP source change requires rebuilding the signed payload.

Sources: [Adobe CEP12 integration/extension folders](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md), [Adobe signing guide](https://github.com/Adobe-CEP/Getting-Started-guides/blob/master/Package%20Distribute%20Install/readme.md), [Adobe Premiere scripting example](https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/jsx/PPRO/Premiere.jsx).
