"""Main-thread Blender data operations. Structural guards are not full edit revisions."""
import hashlib
import json
import math
import os
import secrets
from pathlib import Path

GENERATION=0
SESSION_NONCE=secrets.token_hex(32)


def begin_session():
    """Invalidate old snapshots even when a restarted host reuses PID/object IDs."""
    global SESSION_NONCE
    SESSION_NONCE=secrets.token_hex(32)

def number(v,low=-1e9,high=1e9):
    if type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high:raise ValueError('Finite number outside allowed range')
    return v

def label(v):
    if not isinstance(v,str) or not v.strip() or len(v.encode("utf-8"))>63 or any(ord(c)<32 for c in v):raise ValueError('Name must be 1..63 UTF-8 bytes, printable text')
    return v

def vector(v,size=3,low=-1e9,high=1e9):
    if not isinstance(v,list) or len(v)!=size:raise ValueError('Expected vector of length '+str(size))
    return [number(x,low,high) for x in v]

def state(bpy):
    if len(bpy.data.objects)>50000:raise ValueError('Scene exceeds 50000 object limit')
    if len(bpy.data.collections)>10000:raise ValueError('File exceeds 10000 collection limit')
    if sum(len(c.objects)+len(c.children) for c in [bpy.context.scene.collection,*bpy.data.collections])>100000:raise ValueError('File exceeds 100000 collection membership limit')
    rows=sorted((o.name,o.session_uid,o.type) for o in bpy.data.objects)
    scene={'path':bpy.data.filepath,'modified':bpy.data.is_dirty,'scene':bpy.context.scene.name}
    collections=sorted((c.name,c.session_uid,sorted(o.session_uid for o in c.objects),sorted(x.session_uid for x in c.children)) for c in [bpy.context.scene.collection,*bpy.data.collections])
    digest=hashlib.sha256(json.dumps([SESSION_NONCE,GENERATION,scene,rows,collections],sort_keys=True).encode()).hexdigest()
    return {'scene':scene,'snapshot':digest,'object_count':len(rows),'guard_scope':'bridge session nonce, file path, dirty flag, scene name, object session IDs, collection identities/memberships and bridge file generation; not every property edit'}

def guard(bpy,a):
    if type(a.get('pid')) is not int or a['pid']!=os.getpid():raise ValueError('Explicit current PID required')
    if bpy.context.scene.library or bpy.context.scene.override_library:raise ValueError('Linked/overridden scene protected')
    if a.get('expected_snapshot')!=state(bpy)['snapshot']:raise ValueError('Scene changed; read scene_state again')

def obj(bpy,name,write=False):
    o=bpy.data.objects.get(name)
    if o is None:raise ValueError('Exact object name not found')
    if write and (o.library or o.override_library or (o.data and o.data.library)):raise ValueError('Linked or overridden object is protected')
    return o

def static(o,paths):
    for owner in (o,getattr(o,'data',None)):
        anim=getattr(owner,'animation_data',None)
        if anim and (anim.action or len(anim.drivers) or len(anim.nla_tracks)):raise ValueError('Animated/driven objects require explicit scripting')
    if len(o.constraints):raise ValueError('Constrained object requires explicit scripting')
    for key in paths:
        if key in ('location','rotation_euler','scale') and any(getattr(o,'lock_'+{'location':'location','rotation_euler':'rotation','scale':'scale'}[key])):raise ValueError('Transform component is locked')

def info(o):
    return {'name':o.name,'session_uid':o.session_uid,'type':o.type,'location':list(o.location),'rotation_euler':list(o.rotation_euler),'scale':list(o.scale),'parent':o.parent.name if o.parent else None,'hide_render':o.hide_render,'materials':[m.name if m else None for m in o.data.materials] if o.data and hasattr(o.data,'materials') else []}

def scene_collections(scene):
    return [scene.collection,*scene.collection.children_recursive]

def get_collection(bpy,name,write=False):
    c=bpy.context.scene.collection if not name else bpy.data.collections.get(name)
    if c is None or c not in scene_collections(bpy.context.scene):raise ValueError('Collection is not in the current scene')
    if write:
        if c.library or c.override_library:raise ValueError('Linked or overridden collection protected')
        if any(c in scene_collections(s) for s in bpy.data.scenes if s!=bpy.context.scene):raise ValueError('Collection shared with another scene protected')
    return c

def collection_info(c,scene):
    return {'name':c.name,'session_uid':c.session_uid,'scene_root':c==scene.collection,'children':[x.name for x in c.children],'objects':[o.name for o in c.objects]}

def dispatch(op,a):
    global GENERATION
    import bpy
    if tuple(bpy.app.version[:2])<(4,5):raise ValueError('Blender 4.5+ required')
    scene=bpy.context.scene
    if op=='state':return {**state(bpy),'frame':scene.frame_current,'engine':scene.render.engine}
    reads=op in ('query','assets') or (op in ('material','camera','light','timeline','render_settings','collection') and a.get('action','get')=='get')
    if not reads:guard(bpy,a)
    if op=='query':
        limit=a.get('limit',200)
        if type(limit) is not int or not 1<=limit<=1000:raise ValueError('limit must be1..1000')
        rows=list(bpy.context.selected_objects) if a.get('selected') else list(scene.objects)
        if a.get('object_type'):rows=[o for o in rows if o.type==a['object_type']]
        result={'objects':[info(o) for o in rows[:limit]],'truncated':len(rows)>limit}
    elif op=='file':
        action=a['action']
        if action not in ('new','open','save'):raise ValueError('Use new/open/save')
        if action in ('new','open') and bpy.data.is_dirty and a.get('discard_changes') is not True:raise ValueError('Unsaved changes; save or explicitly authorize discard')
        if action!='new':
            p=Path(a.get('path') or bpy.data.filepath)
            if not p.is_absolute() or p.suffix.lower()!='.blend':raise ValueError('Absolute .blend path required')
            if action=='open' and not p.is_file():raise ValueError('Input does not exist')
            if action=='save' and (not p.parent.is_dir() or (p.exists() and a.get('overwrite') is not True)):raise ValueError('Existing parent and explicit overwrite required')
        if action=='new':response=bpy.ops.wm.read_homefile(use_empty=True);GENERATION+=1
        elif action=='open':response=bpy.ops.wm.open_mainfile(filepath=str(p),load_ui=False,use_scripts=False);GENERATION+=1
        else:response=bpy.ops.wm.save_as_mainfile(filepath=str(p),check_existing=False)
        if 'FINISHED' not in response:raise ValueError('File operation cancelled/failed; inspect before retry')
        result={'action':action,'path':bpy.data.filepath}
    elif op=='create':
        name=label(a['name']);kind=a['kind']
        if bpy.data.objects.get(name):raise ValueError('Object name exists')
        if kind not in ('cube','empty','camera','point_light','sun_light','area_light','mesh'):raise ValueError('Unsupported object kind')
        data=None
        if kind in ('cube','mesh'):
            if kind=='cube':
                verts=[[-1,-1,-1],[-1,-1,1],[-1,1,-1],[-1,1,1],[1,-1,-1],[1,-1,1],[1,1,-1],[1,1,1]];faces=[[0,4,6,2],[1,3,7,5],[0,1,5,4],[2,6,7,3],[0,2,3,1],[4,5,7,6]]
            else:
                verts=a.get('vertices',[]);faces=a.get('faces',[])
                if not isinstance(verts,list) or not isinstance(faces,list) or not 1<=len(verts)<=10000 or len(faces)>10000:raise ValueError('Mesh limit 10000 vertices/faces')
                verts=[vector(v) for v in verts]
                for f in faces:
                    if not isinstance(f,list) or len(f)<3 or len(f)>1000 or any(type(i) is not int or not 0<=i<len(verts) for i in f):raise ValueError('Invalid face indices')
            data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
        elif kind=='camera':data=bpy.data.cameras.new(name)
        elif kind.endswith('_light'):data=bpy.data.lights.new(name,{'point_light':'POINT','sun_light':'SUN','area_light':'AREA'}[kind])
        o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);result=info(o)
    elif op=='edit':
        o=obj(bpy,a['name'],True);action=a['action'];v=a.get('values') or {}
        if action=='transform':
            if not v or set(v)-{'location','rotation_euler','scale'}:raise ValueError('Use location/rotation_euler radians/scale vectors')
            for key,value in v.items():vector(value)
            static(o,v)
            if 'rotation_euler' in v and o.rotation_mode in ('QUATERNION','AXIS_ANGLE'):raise ValueError('Object uses quaternion/axis-angle rotation; Euler edit refused without changing rotation mode')
            for key,value in v.items():setattr(o,key,value)
        elif action in ('rename','duplicate'):
            name=label(a['new_name'])
            if bpy.data.objects.get(name):raise ValueError('Name exists')
            if action=='duplicate':
                o=o.copy()
                if o.data:o.data=o.data.copy()
                scene.collection.objects.link(o)
            o.name=name
        elif action=='visibility':
            if not v or set(v)-{'hide_render','hide_viewport'} or any(type(x) is not bool for x in v.values()):raise ValueError('Boolean hide_render/hide_viewport required')
            for key,value in v.items():setattr(o,key,value)
        elif action=='delete':
            if a.get('confirm_delete') is not True:raise ValueError('Explicit confirm_delete required')
            name=o.name;bpy.data.objects.remove(o,do_unlink=True);return {'result':{'deleted':name},**state(bpy)}
        else:raise ValueError('Unknown edit action')
        result=info(o)
    elif op=='collection':
        action=a.get('action','get');name=a.get('name','')
        if action=='get':
            rows=scene_collections(scene)
            if len(rows)>1000 or sum(len(c.objects) for c in rows)>10000:raise ValueError('Collection listing exceeds 1000 collections/10000 memberships')
            result={'collections':[collection_info(c,scene) for c in rows]}
        elif action=='create':
            label(name)
            if bpy.data.collections.get(name):raise ValueError('Collection name exists')
            parent=get_collection(bpy,a.get('parent',''),True)
            c=bpy.data.collections.new(name);parent.children.link(c);result=collection_info(c,scene)
        else:
            c=get_collection(bpy,name,True)
            if action=='rename':
                if c==scene.collection:raise ValueError('Scene root cannot be renamed here')
                new_name=label(a.get('new_name'))
                if bpy.data.collections.get(new_name):raise ValueError('Collection name exists')
                c.name=new_name
            elif action in ('link','unlink'):
                o=obj(bpy,a.get('object_name'),True)
                if o.name not in scene.objects:raise ValueError('Object is not in the current scene')
                if action=='link':
                    if o.name in c.objects:raise ValueError('Object is already linked')
                    c.objects.link(o)
                else:
                    if o.name not in c.objects:raise ValueError('Object is not linked to this collection')
                    if not any(other!=c and other in scene_collections(scene) for other in o.users_collection):raise ValueError('Unlink would remove object from current scene; link destination first')
                    c.objects.unlink(o)
            else:raise ValueError('Use get/create/rename/link/unlink')
            result=collection_info(c,scene)
    elif op=='parent':
        o=obj(bpy,a['name'],True);parent=obj(bpy,a['parent'],True) if a.get('parent') else None
        if o.name not in scene.objects or (parent and parent.name not in scene.objects):raise ValueError('Parent and child must be in the current scene')
        if len(o.users_scene)>1:raise ValueError('Object shared with another scene protected')
        static(o,('location','rotation_euler','scale'))
        if o.parent and o.parent_type!='OBJECT':raise ValueError('Bone/vertex parenting requires explicit scripting')
        ancestor=parent
        while ancestor:
            if ancestor==o:raise ValueError('Parenting cycle refused')
            ancestor=ancestor.parent
        bpy.context.view_layer.update()
        if parent and abs(parent.matrix_world.determinant())<1e-12:raise ValueError('Parent has singular world transform')
        world=o.matrix_world.copy();old_parent=o.parent;old_inverse=o.matrix_parent_inverse.copy();old_basis=o.matrix_basis.copy()
        o.parent=parent;o.parent_type='OBJECT'
        if parent:o.matrix_parent_inverse=parent.matrix_world.inverted()
        else:o.matrix_parent_inverse.identity()
        o.matrix_basis=world
        bpy.context.view_layer.update()
        if any(abs(o.matrix_world[r][c]-world[r][c])>1e-4 for r in range(4) for c in range(4)):
            o.parent=old_parent;o.matrix_parent_inverse=old_inverse;o.matrix_basis=old_basis
            bpy.context.view_layer.update();raise ValueError('World transform could not be preserved; original parenting restored')
        result=info(o)
    elif op=='selection':
        names=a.get('names',[])
        if not isinstance(names,list) or len(names)>1000:raise ValueError('Selection max1000')
        objects=[obj(bpy,n) for n in names]
        if any(o.name not in bpy.context.view_layer.objects for o in objects):raise ValueError('Object outside current view layer')
        for o in bpy.context.view_layer.objects:o.select_set(o in objects)
        bpy.context.view_layer.objects.active=objects[0] if objects else None;result={'selected':names}
    elif op=='material':
        action=a.get('action','get');name=a['name'];m=bpy.data.materials.get(name)
        if action=='create':
            label(name)
            if m:raise ValueError('Material exists')
        elif m is None:raise ValueError('Material not found')
        if action in ('create','set'):
            if m and (m.library or m.override_library):raise ValueError('Linked material protected')
            values=a.get('values') or {};allowed={'diffuse_color':(4,0,1),'roughness':(None,0,1),'metallic':(None,0,1)}
            if not values or set(values)-set(allowed):raise ValueError('Use diffuse_color RGBA, roughness or metallic')
            for key,value in values.items():
                count,low,high=allowed[key];vector(value,count,low,high) if count else number(value,low,high)
            if m and m.animation_data:raise ValueError('Animated material protected')
            if m and m.use_nodes:raise ValueError('Node material editing requires explicit scripting; these are viewport/basic surface properties')
            if m is None:m=bpy.data.materials.new(name)
            for key,value in values.items():setattr(m,key,value)
        elif action=='assign':
            o=obj(bpy,a['object_name'],True)
            if not o.data or not hasattr(o.data,'materials'):raise ValueError('Object has no material slots')
            if o.data.users>1:raise ValueError('Shared data; duplicate data explicitly before assigning')
            if m not in list(o.data.materials):o.data.materials.append(m)
        elif action!='get':raise ValueError('Use get/create/set/assign')
        result={'name':m.name,'use_nodes':m.use_nodes,'diffuse_color':list(m.diffuse_color),'roughness':m.roughness,'metallic':m.metallic}
    elif op in ('camera','light'):
        o=obj(bpy,a['name'],a.get('action','get')!='get');required='CAMERA' if op=='camera' else 'LIGHT'
        if o.type!=required:raise ValueError('Wrong object type')
        allowed={'lens':(1,5000),'clip_start':(.001,1e6),'clip_end':(.001,1e9)} if op=='camera' else {'energy':(0,1e9),'color':(0,1)}
        if a.get('action','get')=='set':
            values=a.get('values') or {}
            if not values or set(values)-set(allowed):raise ValueError('Unsupported camera/light setting')
            if o.data.users>1:raise ValueError('Shared camera/light data protected')
            static(o,[])
            for key,value in values.items():vector(value,3,0,1) if key=='color' else number(value,*allowed[key])
            if op=='camera' and values.get('clip_start',o.data.clip_start)>=values.get('clip_end',o.data.clip_end):raise ValueError('clip_start must be below clip_end')
            for key,value in values.items():setattr(o.data,key,value)
        elif a.get('action','get')=='activate' and op=='camera':scene.camera=o
        elif a.get('action','get')!='get':raise ValueError('Unsupported action')
        result={'name':o.name,**{key:list(getattr(o.data,key)) if key=='color' else getattr(o.data,key) for key in allowed}}
    elif op=='timeline':
        if a.get('action','get')=='set':
            values=a.get('values') or {}
            if not values or set(values)-{'frame_start','frame_end','frame_current','fps'}:raise ValueError('Unsupported timeline setting')
            for key,value in values.items():
                if type(value) is not int:raise ValueError('Integer timeline values required')
                number(value,1 if key=='fps' else -1048574 if key=='frame_current' else 0,32767 if key=='fps' else 1048574)
            if values.get('frame_start',scene.frame_start)>values.get('frame_end',scene.frame_end):raise ValueError('Invalid frame range')
            for key,value in values.items():
                if key=='fps':scene.render.fps=value
                elif key=='frame_current':scene.frame_set(value)
                else:setattr(scene,key,value)
        elif a.get('action','get')!='get':raise ValueError('Use get/set')
        result={k:getattr(scene,k) for k in ('frame_start','frame_end','frame_current')};result['fps']=scene.render.fps
    elif op=='render_settings':
        if a.get('action','get')=='set':
            values=a.get('values') or {}
            if not values or set(values)-{'resolution_x','resolution_y','resolution_percentage','engine'}:raise ValueError('Unsupported setting; no render/output writes')
            for key,value in values.items():
                if key=='engine':
                    if value not in {'BLENDER_EEVEE_NEXT','CYCLES','BLENDER_WORKBENCH'}:raise ValueError('Unsupported engine')
                elif type(value) is not int or not (1 if key=='resolution_percentage' else 4)<=value<=(100 if key=='resolution_percentage' else 16384):raise ValueError('Invalid resolution')
            if 'engine' in values:scene.render.engine=values['engine']
            for key,value in values.items():
                if key!='engine':setattr(scene.render,key,value)
        elif a.get('action','get')!='get':raise ValueError('Use get/set')
        result={k:getattr(scene.render,k) for k in ('resolution_x','resolution_y','resolution_percentage','engine')}
    elif op=='assets':
        rows=[]
        for collection in (bpy.data.images,bpy.data.movieclips,bpy.data.sounds,bpy.data.libraries):
            for item in collection:
                if len(rows)>=10000:raise ValueError('Asset limit10000')
                path=getattr(item,'filepath','');packed=bool(getattr(item,'packed_file',None) or getattr(item,'packed_files',None))
                source=getattr(item,'source','FILE');resolved=bpy.path.abspath(path,library=getattr(item,'library',None)) if path else ''
                status='packed' if packed else 'unverified' if source in ('GENERATED','VIEWER','TILED','SEQUENCE') or not path else 'present' if Path(resolved).is_file() else 'missing'
                rows.append({'name':item.name,'path':path,'resolved':resolved,'status':status})
        result={'assets':rows,'coverage':'Images, movie clips, sounds and linked libraries. Sequence/UDIM completeness, caches/fonts and compositor outputs are not verified.'}
    else:raise ValueError('Unsupported operation')
    return {'result':result,**state(bpy)}
