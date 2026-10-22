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

## 更新和卸载的两层范围

GitHub 发布后需刷新已注册的 Codex 插件市场，并重新加载聊天或重启 Codex。软件/项目中的桥接独立保存，需预览差异、经同意后更新，再重启或使用该软件支持的刷新方式。完整卸载请先通过本插件工具卸载软件端桥接，再从 Codex 移除插件；只卸载 Codex 插件会保留软件端配置。Windows 旧版缓存被占用时，先停掉明确属于该插件的旧 MCP 进程，再重试，勿关闭创作软件或批量删除配置。

## Structured editing in 0.2.0

Prefer `unity_list_objects`, `unity_inspect_object`, `unity_object_action`, `unity_scene_action`, and `unity_settings` for supported routine work instead of generating scripts. List objects first and retain both the explicit PID and returned `scene_token`; pass that token as `expected_scene`. IDs are GameObject instance IDs, guarded by loaded/active scene handles and a random epoch invalidated by scene open/close/new events; they are not portable asset GUIDs. Re-query after scene/level changes or reconnect.

The object action supports create, select, duplicate, rename, delete, and position/scale transforms. Creation kinds: cube, sphere, plane, capsule, cylinder, quad, empty. Transforms use host world position and local scale; this release does not provide rotation, reparenting, animation/keyframe editing or arbitrary property assignment. Inspection returns hierarchy and component/modifier/material metadata, not a complete serialized property editor. Delete only when authorized. Errors and timeouts may follow partial work; never retry mutations automatically.

New/open refuse dirty affected scenes (Unreal also refuses dirty content packages), without implicitly saving or discarding anything. Save requires an explicit destination; replacing any existing file requires `overwrite=true` and user authorization. Unity new/open replaces all loaded scenes after checking every scene for unsaved changes. No build or render starts from the settings query.

Update the application-side bridge through the setup tool and restart/reload the relevant application after updating the Codex plugin; an old running bridge does not gain new operations automatically. Existing owned-file update and removal protections remain in place.

API references: [Unity 6000.1 EditorSceneManager](https://docs.unity3d.com/6000.1/Documentation/ScriptReference/SceneManagement.EditorSceneManager.html). Signatures compile against installed 6000.1 editor assemblies.

Validation: 17 Python regressions, actual Unity 6000.1 assembly compilation, and production C# protocol with two mock Editors pass; structured create/transform/rename/duplicate/delete, dirty-scene refusal, save/overwrite and stale-scene-token checks are included. Real MCP stdio exposes 14 tools. Mock scenes are not native Unity Editor acceptance; that remains pending.
