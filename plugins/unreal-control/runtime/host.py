"""Unreal Editor 5.5 host adapter; never loads or saves assets during inspection."""
import os
import queue

_tick = None
_shutdown = None
_queue = queue.Queue(maxsize=64)

_identity_world = None
_identity_token = None
_observed_actors = {}


def scene_token():
    import uuid
    import unreal
    global _identity_world, _identity_token
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world != _identity_world or _identity_token is None:
        _identity_world, _identity_token = world, uuid.uuid4().hex
        _observed_actors.clear()
    return _identity_token


def structured(operation, a):
    import math
    import re
    import unreal
    ensure_script_allowed()
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    scene_token()
    def vec(v):
        if not isinstance(v, list) or len(v) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v): raise ValueError('Expected three finite numbers')
        return unreal.Vector(*v)
    def xyz(v): return [v.x, v.y, v.z]
    def row(n):
        _observed_actors[n.get_path_name()] = n
        parent = n.get_attach_parent_actor()
        return {'id': n.get_path_name(), 'name': n.get_actor_label(), 'class': n.get_class().get_path_name(), 'parent_id': parent.get_path_name() if parent else None, 'folder': str(n.get_folder_path()), 'position': xyz(n.get_actor_location()), 'scale': xyz(n.get_actor_scale3d()), 'rotation': [n.get_actor_rotation().pitch, n.get_actor_rotation().yaw, n.get_actor_rotation().roll]}
    if operation == 'list_objects':
        limit = a.get('limit', 1000)
        if type(limit) is not int or not 1 <= limit <= 5000: raise ValueError('limit must be 1..5000')
        nodes = list(actors.get_all_level_actors())
        return {'objects': [row(n) for n in nodes[:limit]], 'truncated': len(nodes) > limit, 'scene_token': scene_token(), 'scene': scene_info()}
    if operation == 'settings':
        return {'engine': unreal.SystemLibrary.get_engine_version(), 'world_settings_class': world.get_world_settings().get_class().get_path_name(), 'dirty_maps': [x.get_path_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()], 'dirty_assets': [x.get_path_name() for x in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]}
    if a.get('expected_scene') != scene_token(): raise ValueError('World changed; list objects again')
    action = a.get('action')
    if operation == 'scene_action':
        api = unreal.EditorLoadingAndSavingUtils
        if action in ('new', 'open') and (api.get_dirty_map_packages() or api.get_dirty_content_packages()): raise ValueError('Dirty maps/content exist; save explicitly first')
        if action == 'new':
            if not api.new_blank_map(False): raise RuntimeError('New map failed')
        elif action in ('open', 'save'):
            package = a.get('path') or ''
            if not re.fullmatch(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+', package): raise ValueError('Use a /Game/Folder/Map long package name')
            disk = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()), package[6:] + '.umap')
            if action == 'open':
                if not os.path.isfile(disk): raise ValueError('Map does not exist')
                if not api.load_map(disk): raise RuntimeError('Open map failed')
            else:
                if os.path.exists(disk) and not a.get('overwrite'): raise ValueError('Existing map requires overwrite=true')
                if not api.save_map(world, package): raise RuntimeError('Save map failed')
        else: raise ValueError('Unknown scene action')
        return {'scene': scene_info(), 'scene_token': scene_token()}
    nodes = {n.get_path_name(): n for n in actors.get_all_level_actors()}
    if operation == 'object_action' and action == 'create':
        kinds = {'actor': unreal.Actor, 'point_light': unreal.PointLight, 'camera': unreal.CameraActor, 'static_mesh': unreal.StaticMeshActor}
        if a.get('kind') not in kinds: raise ValueError('Unsupported actor kind')
        n = actors.spawn_actor_from_class(kinds[a['kind']], unreal.Vector(0, 0, 0))
        if not n: raise RuntimeError('Actor creation failed')
        if a.get('name'): n.set_actor_label(a['name'])
        return row(n)
    n = nodes.get(a.get('object_id'))
    if n is None: raise ValueError('Actor is not in the current editor world')
    if _observed_actors.get(a.get('object_id')) != n: raise ValueError('Actor identity changed; list objects again')
    if operation == 'inspect_object':
        data = row(n); data['components'] = [{'name': x.get_name(), 'class': x.get_class().get_path_name()} for x in n.get_components_by_class(unreal.ActorComponent)][:500]
        return data
    if operation != 'object_action': raise ValueError('Unknown structured operation')
    with unreal.ScopedEditorTransaction('Bubble actor edit'):
        if action == 'select': actors.set_selected_level_actors([n])
        elif action == 'duplicate':
            n = actors.duplicate_actor(n)
            if not n: raise RuntimeError('Duplicate failed')
        elif action == 'rename':
            if not isinstance(a.get('name'), str) or not a['name'].strip(): raise ValueError('Nonempty label required')
            n.set_actor_label(a['name'])
        elif action == 'delete':
            identity = n.get_path_name()
            if not actors.destroy_actor(n): raise RuntimeError('Delete failed')
            return {'deleted_id': identity}
        elif action == 'transform':
            values = {k: vec(a[k]) for k in ('position', 'scale', 'rotation') if a.get(k) is not None}
            if not values: raise ValueError('Specify position, rotation or scale')
            n.modify()
            if 'position' in values:
                n.set_actor_location(values['position'], False, True)
                actual = n.get_actor_location()
                if any(abs(getattr(actual,k)-getattr(values['position'],k))>0.001 for k in ('x','y','z')): raise RuntimeError('Actor rejected requested location; inspect before retrying')
            if 'scale' in values: n.set_actor_scale3d(values['scale'])
            if 'rotation' in values:
                v=values['rotation']
                if not n.set_actor_rotation(unreal.Rotator(pitch=v.x,yaw=v.y,roll=v.z), True): raise RuntimeError('Actor rejected rotation; inspect before retrying')
        elif action == 'parent':
            parent_id=a.get('parent_id')
            parent=nodes.get(parent_id) if parent_id else None
            if parent_id and (parent is None or _observed_actors.get(parent_id)!=parent): raise ValueError('Parent identity is not observed in current world; list objects again')
            if parent and parent.get_level()!=n.get_level(): raise ValueError('Parent and child must belong to the same level')
            ancestor=parent
            while ancestor:
                if ancestor==n: raise ValueError('Parenting cycle refused')
                ancestor=ancestor.get_attach_parent_actor()
            n.modify()
            if parent:
                rule=unreal.AttachmentRule.KEEP_WORLD
                n.attach_to_actor(parent,unreal.Name(''),rule,rule,rule,False)
            else:
                rule=unreal.DetachmentRule.KEEP_WORLD
                n.detach_from_actor(rule,rule,rule)
            if n.get_attach_parent_actor()!=parent: raise RuntimeError('Actor rejected parenting; inspect before retrying')
        elif action == 'folder':
            folder=a.get('folder')
            if not isinstance(folder,str) or len(folder)>512 or folder.lower()=='none' or any(ord(c)<32 for c in folder) or (folder and any(not part.strip() or part in ('.','..') for part in folder.split('/'))) or '\\' in folder: raise ValueError('Use relative Outliner folder path with slash-separated names, or empty string to clear; None is a reserved Unreal name')
            n.modify();n.set_folder_path(unreal.Name(folder))
            if str(n.get_folder_path()) not in (folder,'None' if not folder else folder): raise RuntimeError('Actor rejected folder; inspect before retrying')
        else: raise ValueError('Unknown object action')
    return row(n)


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
    try:
        _shutdown = unreal.register_python_shutdown_callback(stop)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_tick)
        _tick = None
        raise
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
