"""Unreal Editor 5.5 host adapter; never loads or saves assets during inspection."""
import os
import queue

_tick = None
_shutdown = None
_queue = queue.Queue(maxsize=64)


def is_interactive():
    import re
    import unreal
    command = unreal.SystemLibrary.get_command_line()
    return unreal.is_editor() and not re.search(r"(?:^|\s)-(?:run\s*=|game\b|server\b|unattended\b)", command, re.I)


def ensure_script_allowed():
    import unreal
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        raise RuntimeError("Stop Play In Editor before executing Bubble scripts; no script was started")


def scene_info():
    import unreal
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    package = world.get_path_name().split(".")[0] if world else ""
    # Untitled transient worlds have no saved file identity.
    path = "" if package.startswith("/Temp/") else package
    if package.startswith("/Game/"):
        path = os.path.abspath(os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()), package[len("/Game/"):] + ".umap"))
    dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
    return {"path": path, "map_package": package,
            "modified": any(item.get_path_name() == package for item in dirty),
            "project": os.path.abspath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())),
            "unreal_version": unreal.SystemLibrary.get_engine_version(),
            "play_in_editor": bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()),
            "selection": [actor.get_path_name() for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()],
            "dirty_content_packages": [item.get_path_name() for item in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]}


def inspect_scene(package=None):
    import unreal
    scene = scene_info()
    package = package or (scene["map_package"] if scene["path"] else "")
    if not package or not package.startswith("/") or "." in package:
        raise ValueError("A saved map or explicit long package name such as /Game/Props/Chair is required")
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    if registry.is_loading_assets():
        return {"scene": scene, "complete": False, "dependencies": [],
                "warning": "Asset Registry is still scanning; inspect again after it finishes."}
    if not registry.get_assets_by_package_name(package):
        return {"scene": scene, "package": package, "complete": False, "dependencies": [],
                "warning": "Root package is not registered. Verify the saved package name; no dependency verdict is available."}
    options = unreal.AssetRegistryDependencyOptions(include_soft_package_references=True,
                                                  include_hard_package_references=True,
                                                  include_searchable_names=False,
                                                  include_soft_management_references=False,
                                                  include_hard_management_references=False)
    assets = []
    for dependency in registry.get_dependencies(package, options) or []:
        name = str(dependency)
        if name.startswith("/Script/"):
            continue
        assets.append({"package": name, "registered": bool(registry.get_assets_by_package_name(name))})
    return {"scene": scene, "package": package, "complete": True, "dependencies": assets,
            "unresolved_packages": [item["package"] for item in assets if not item["registered"]],
            "coverage": "Direct hard/soft package references in the current Asset Registry. No asset loading, saving, compilation or rescan. Unresolved registry packages are warnings, not proof of missing disk files; excludes external source files and transitive dependencies."}


def install_dispatcher(stop):
    global _tick, _shutdown
    import unreal
    import threading
    if threading.current_thread() is not threading.main_thread() or not is_interactive():
        raise RuntimeError("Bridge requires interactive Unreal Editor on its main thread")
    def drain(delta):
        for _ in range(8):
            try:
                callback = _queue.get_nowait()
            except queue.Empty:
                break
            callback()
    _tick = unreal.register_slate_post_tick_callback(drain)
    _shutdown = unreal.register_python_shutdown_callback(stop)
    return _queue.put_nowait


def remove_dispatcher():
    global _tick, _shutdown
    import unreal
    if _tick is not None:
        unreal.unregister_slate_post_tick_callback(_tick)
        _tick = None
    if _shutdown is not None:
        unreal.unregister_python_shutdown_callback(_shutdown)
        _shutdown = None
    while not _queue.empty():
        try:
            _queue.get_nowait()
        except queue.Empty:
            break
