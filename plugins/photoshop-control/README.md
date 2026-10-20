# Bubble Photoshop

Photoshop **26.2+** (2025) UXP integration. The detected Photoshop 2021 / 22.0 installation is intentionally outside this package's scope. Version 0.1.0.

## Architecture and operation

Codex runs a stdio MCP server in uv's locked external script environment. A Photoshop UXP panel connects by authenticated HTTP to a random loopback port owned by that MCP process. User enters a private connection code in the panel; no Script Editor code, Node-in-host, CEP debug registry changes or arbitrary JavaScript eval are used.

The panel must stay open. Credentials are in memory, not persistent storage. Restarting MCP requires a new pairing code. Each paired panel has a random session UUID; it is not an OS PID. Only paired panels are visible. Document names, full paths and IDs allow explicit selection across panels; duplicate/unsaved/ambiguous targets are not guessed.

Tools inspect document properties and bounded layer lists, and run authorized batchPlay descriptors inside executeAsModal. The selected document must remain active at execution. Descriptors can still affect other documents/application state: target checks are not a permissions sandbox. No automatic mutation retry; a timeout may follow partial changes.

## Install / update / uninstall

The setup skill first shows installation_status and install_bridge(confirmed=false). A reproducible candidate CCX is included under adobe/ so users do not need to package source first. It follows Adobe's documented ZIP-based CCX structure, but has not been validated by UDT or a native Adobe installation in this environment. The installer checks all package contents against this release, then delegates to official Adobe tools with consent. An optional absolute package_path accepts a matching UDT-built package. Having a CCX is not proof of Adobe installation; real panel loading and pairing must be checked. Adobe UI/UXP Developer Tool steps may be required. This repository does not silently enable developer mode, change security preferences or overwrite Adobe's private plugin storage.

Open the installed Bubble Photoshop panel through Photoshop's Plugins menu, obtain photoshop_pairing in Codex, paste its private code and Connect. Keep it private. Reopening a panel creates a new session identity.

Update through the same preview/confirmed workflow; close/reopen the panel when Adobe requires. Uninstall previews before official Adobe removal without deleting source packages or Adobe private files. Removing the Codex plugin does not remove the Adobe panel; disconnect and uninstall the bridge first if both should be removed. No host is restarted or killed automatically.

## Limits

- Layer inventory is not a missing-font or linked-smart-object dependency audit.
- No unrestricted file access permission: file-based descriptors require appropriate UXP file tokens/permissions and are not guaranteed to work with raw paths.
- No arbitrary JS/ExtendScript execution; use documented batchPlay descriptors.
- Automated tests use mocked Photoshop APIs and real MCP/HTTP plumbing. They do not prove native Adobe panel installation or graphical host behavior.

## References

- [Adobe UXP install](https://developer.adobe.com/uxp/guides/how-to/distribution/install/)
- [Photoshop executeAsModal](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/media/executeasmodal/)
- [Photoshop batchPlay](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/media/batchplay/)
- [Photoshop Document API](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/classes/document)
- [Manifest v5 permissions](https://developer.adobe.com/photoshop/uxp/2022/guides/uxp-guide/uxp-misc/manifest-v5/)

Icon: extracted from the locally installed Adobe Photoshop executable; Adobe trademark, used for application identification. See assets/SOURCE.md.
