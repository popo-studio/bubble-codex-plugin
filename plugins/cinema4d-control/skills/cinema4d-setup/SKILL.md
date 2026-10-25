---
name: cinema4d-setup
description: Set up, update, remove or troubleshoot Bubble Cinema 4D connections using Maxon's built-in MCP server in Cinema 4D 2027.
---

# Cinema 4D setup

Use `cinema4d_setup_status` first. This package uses the native Maxon MCP server; do not install a custom .pyp, invent a publisher ID, open raw command ports or copy code into an editor. No older-version bridge is provided.

In full Cinema 4D 2027, ask the user to enable Preferences → MCP → Server → Allow MCP Server and accept Maxon's prompt. It starts immediately. Use Clients → Other → Copy Config or an existing Maxon-created standard MCP JSON config. Keep the exported config in a private local file. Never print credentials or request that the user paste them into chat. Do not guess paths, executable arguments, URL paths, ports or authentication headers. Unknown export formats are unsupported until verified; explain that and obtain only a credential-free field structure.

Register the exact file/entry with `cinema4d_configure` using confirmed=false. Show connection name, source file, transport and the fact that stdio will launch its program. Only after user authorization, repeat with confirmed=true and both returned preview hashes. Read-only setup inquiry is not permission for persistent setup or arbitrary executable launch. Do not automatically execute discovered JSON files. Standard supported transports are stdio and local loopback HTTP/SSE. External endpoints, unknown credential mechanisms and config variable expansion are not supported.

Call `cinema4d_connect` after authorization, then `cinema4d_discover_tools` for the returned session. No host installation or restart is needed. Native C4D is absent from the development machine: the exported configuration format and native operations still require real acceptance. Never say fixture tests prove actual Cinema 4D operation.

Authorization persists: `authorized=true` carries the user's current operation request or existing authorization for this unchanged trusted registration. Do not ask for pairing/confirmation on every routine connection. A current request can authorize connecting the sole registered trusted endpoint. Explicit session selection is a tool-level action; ask the user only when target/scope is ambiguous. A lost connection never authorizes replaying writes; reconnect only to re-establish and inspect state before deciding a genuinely new action.

Multiple instances need separate native ports/config exports and named registrations. Show connections and inspect native document identities before choosing; ask if ambiguous. Do not identify a process by an assumed port or treat the adapter session_id as an OS PID. Configuration changes including token rotation require re-preview/authorization. Never silently reconnect a stale session for writes.

To remove: disconnect the chosen session, preview `cinema4d_configure(action="remove", name=...)`, confirm only with authorization. Only Bubble's registration is removed; exported files and native preferences are retained. To stop native listening, use Maxon's Stop MCP Server / Allow MCP Server. Codex uninstall removes this package separately. Update Bubble through its marketplace and the native service through Cinema 4D updates.
