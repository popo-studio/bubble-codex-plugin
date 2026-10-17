# Bubble Unity Control

Connect Codex to a selected Unity 6 Editor project. Each Editor uses a different random loopback port, authentication token and PID record. Show project and scene names when selecting among Editors; no shared fixed port and no automatic failover.

The target tested at build time is Windows Unity **6000.1.0f1**. The installer accepts Unity 6 (`6000.x`) on Windows. Both installer and bridge reject other operating systems in this release. Other Unity versions are not claimed as validated. Install `uv` for the Codex-side Python MCP server. The Editor package has no downloaded runtime dependencies and is excluded from player builds by its Editor-only assembly definition.

## Installation

Ask Codex to connect to Unity and provide the existing project's absolute directory. The setup tool previews the exact changes first. With your permission it copies `unity/` to `<project>/Packages/com.bubble.codex-control`, plus an ownership manifest. It does not edit `Packages/manifest.json` or scene files. Embedded packages are discovered by Unity without a manifest entry.

Save your work and restart that Editor after installation. If you prefer not to restart, return to Unity and wait for automatic package refresh and C# compilation, or use **Assets > Refresh**. Codex then rediscovers the same project. Compilation errors in existing project scripts can prevent the bridge loading. No manual Python paste is involved; Unity does not have Maya's Python Script Editor.

The Tools > Bubble menu can start/stop the bridge. It stops for domain reload, quit and entering Play Mode, then reconnects in Edit Mode. Batch mode is disabled by default. The test-only environment override `BUBBLE_UNITY_ALLOW_BATCH=1` enables isolated batch fixtures.

Uninstall through `unity_uninstall_bridge`, preview then authorize. Only owned unmodified files are removed. User-modified package files cause a conflict; `.meta` files and unrelated contents are preserved. Refresh/restart Unity after removal. Uninstalling the Codex plugin does not remove the embedded project package.

## Tools

| Tool | Purpose |
| --- | --- |
| `unity_installation_status` | Read-only installation preview for an explicit project |
| `unity_install_bridge` / `unity_uninstall_bridge` | Consent-gated project package changes |
| `unity_list_sessions` | Live projects, loaded scenes, exact filename/project matching |
| `unity_status` / `unity_scene_info` | Version, project, scenes, selection, compile/import/play state |
| `unity_inspect_scene` | Loaded-scene missing scripts and serialized missing references |
| `unity_invoke_method` | Execute an existing public static C# Editor method |
| `unity_execute_menu` | Execute an authorized exact Editor menu path |

For multiple Editors, choose a numbered project/scene row or provide an exact filename/full path. Duplicate scene names require project/path disambiguation. Unsaved scenes display as `未保存场景`. Only connected bridges are listed. An unreachable record blocks automatic filename selection. A selected PID never falls back to another Editor after failure.

Scene inspection is read-only and bounded at 5,000 objects by default (configurable to 10,000) and 5,000 issues. It reports truncation and excludes unloaded scenes, prefab assets, Addressables and external dependency completeness. It does not save/import/fix anything.

## C# scripting

This version invokes compiled methods; it is **not an arbitrary C# eval console**. A method must be public static, synchronous, and accept zero arguments or one string. It may return void, string, a primitive or enum. Return JSON as a string for structured results. Task/coroutine methods are rejected. Unity Console output is not captured.

For example, after you authorize adding `Assets/Editor/BubbleExample.cs` to your project:

```csharp
public static class BubbleExample
{
    public static string DescribeSelection()
    {
        return UnityEditor.Selection.activeObject == null
            ? "Nothing selected" : UnityEditor.Selection.activeObject.name;
    }
}
```

Wait for Unity to compile and reconnect, then call `unity_invoke_method(type_name="BubbleExample", method_name="DescribeSelection", pid=<selected PID>)`. A payload selects a method with exactly one string parameter. C# method and menu calls run on the Editor main thread with the user's full file/network privileges; they are not sandboxed. Timeout cannot undo running code. Queued expired work is cancelled; work that already started may finish after timeout. Never automatically repeat a mutation after errors/disconnect/reload.

## Validation and API references

`tests/test_unity.py` covers project install ownership/rollback, exact selection and authenticated client routing using scratch fixtures. `tests/protocol_smoke.py` compiles the production C# transport with Unity API test doubles and exercises two independent processes, authentication, main-thread dispatch, queued cancellation, running timeouts, busy guards, async rejection and reload cleanup. `tests/editor_smoke.py` compiles the bridge against installed Unity assemblies, then optionally uses `--run-editor` for an isolated batch project (requires a usable Unity license). It never uses a user's existing project. The initial real Editor smoke attempt was blocked by this machine's missing Unity Editor license; actual Unity scene execution has not been claimed as passing. Interactive Editor restart, menu dialogs, real production asset coverage and Play Mode transitions still need manual acceptance testing.

Official APIs used: [embedded packages](https://docs.unity3d.com/6000.1/Documentation/Manual/upm-embed.html), [InitializeOnLoad](https://docs.unity.cn/6000.1/Documentation/ScriptReference/InitializeOnLoadAttribute.html), [Editor update](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/EditorApplication-update.html), [assembly reload](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/AssemblyReloadEvents-beforeAssemblyReload.html), [Play Mode changes](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/EditorApplication-playModeStateChanged.html), [menu execution](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/EditorApplication.ExecuteMenuItem.html), [missing scripts](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/GameObjectUtility.GetMonoBehavioursWithMissingScriptCount.html), [thread-safe plain-object JSON parsing](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/JsonUtility.FromJson.html).
