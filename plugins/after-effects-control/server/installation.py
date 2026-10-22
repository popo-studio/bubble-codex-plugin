"""Exact owned Startup JSX installation; no Adobe preferences or developer tools."""
import hashlib
import json
import os
from pathlib import Path
import uuid
import re
import time
from contextlib import contextmanager
from native import installations
from privacy import runtime_directory,safe_path,protect_directory

ROOT=Path(__file__).resolve().parents[1]
# Snapshot source at import, so a running MCP survives removal of its package.
SOURCE='\n'.join((ROOT/'host'/name).read_text(encoding='utf-8') for name in ['operations.jsx','bridge.jsx'])


def receipt():
    p=safe_path(runtime_directory()/'receipt.json')
    if not p.exists():return None
    if p.stat().st_size>65536:raise ValueError('Installation receipt is too large')
    r=json.loads(p.read_text(encoding='utf-8'))
    if r.get('schema')!=1 or r.get('version') not in ('0.2.0','0.3.0') or not r.get('target') or r.get('profile')!=os.environ.get('LOCALAPPDATA'):
        raise ValueError('Unknown installation receipt; inspect before modifying')
    return r


def failure(code,message):return {'ok':False,'error':{'code':code,'message':str(message)}}


def cleanup_runtime():
    """Remove recognized owned IPC only; retain live running requests and unknown files."""
    root=safe_path(runtime_directory()/'hosts');removed=[];retained=[]
    if not root.exists():return {'removed_files':removed,'retained_files':retained}
    def read(p):
        safe_path(p)
        if p.stat().st_size>8*1024*1024:raise ValueError('Oversized runtime file')
        return json.loads(p.read_text(encoding='utf-8-sig'))
    for folder in list(root.iterdir())[:256]:
        if not re.fullmatch('[0-9a-f]{32}',folder.name):continue
        safe_path(folder);owner=folder/'.owner.json'
        try:
            data=read(owner)
            if data.get('schema')!=1 or data.get('session_id')!=folder.name or data.get('bridge_version') not in ('0.2.0','0.3.0') or not re.fullmatch('[0-9a-f]{32}',str(data.get('installation_id',''))):continue
        except (OSError,ValueError):continue
        heartbeat=folder/'heartbeat.json'
        if heartbeat.exists():
            try:
                if read(heartbeat).get('session_id')==folder.name:heartbeat.unlink();removed.append(str(heartbeat))
            except (OSError,ValueError):retained.append(str(heartbeat))
        for name in ['requests','results']:
            child=safe_path(folder/name)
            if not child.exists():continue
            for p in list(child.iterdir())[:256]:
                if not re.fullmatch('[0-9a-f]{32}\\.(json|running)',p.name):retained.append(str(p));continue
                try:
                    q=read(p)
                    if q.get('request_id')!=p.stem or (name=='requests' and q.get('session_id')!=folder.name):retained.append(str(p));continue
                    if p.suffix=='.running' and q.get('expires_at',float('inf'))>time.time()*1000:retained.append(str(p));continue
                    p.unlink();removed.append(str(p))
                except (OSError,ValueError,TypeError):retained.append(str(p))
            if not any(child.iterdir()):child.rmdir()
        if set(p.name for p in folder.iterdir())=={'.owner.json'}:owner.unlink();folder.rmdir()
    return {'removed_files':removed,'retained_files':retained}


def plan(executable=None):
    apps=installations()
    available=[a for a in apps if int(a.get('major') or 0)==26]
    current=receipt()
    if executable is None and current:executable=current['executable']
    if executable is None and len(available)==1:executable=available[0]['executable']
    selected=next((a for a in available if executable and os.path.normcase(a['executable'])==os.path.normcase(str(Path(executable).resolve()))),None)
    if not selected:raise ValueError('Choose the exact verified AE 26 executable from installation_status; unsupported or ambiguous installation')
    exe=safe_path(Path(selected['executable']).resolve())
    if exe.name.lower()!='afterfx.exe' or exe.parent.name.lower()!='support files':raise ValueError('Unexpected AE installation layout')
    startup=safe_path(exe.parent/'Scripts'/'Startup')
    if not startup.is_dir():raise ValueError('Verified Scripts/Startup directory does not exist')
    suffix=hashlib.sha256(os.environ['LOCALAPPDATA'].casefold().encode()).hexdigest()[:12]
    target=safe_path(startup/('BubbleAfterEffects-'+suffix+'.jsx'))
    if current and Path(current['target'])!=target:raise ValueError('A different AE installation is managed. Uninstall that bridge explicitly before selecting another; no other configuration is overwritten')
    if target.exists() and (not current or hashlib.sha256(target.read_bytes()).hexdigest()!=current['sha256']):raise ValueError('Startup file is unowned or modified; refusing to overwrite')
    return target,current,selected


def status(executable=None):
    try:
        data={'version':'0.3.0','installations':installations(),'receipt':receipt(),'transport':'managed Startup JSX + per-instance private file IPC','requires_creative_cloud':False,'requires_developer_mode':False,'required_preference':'Allow Scripts to Write Files and Access Network (enable once manually)','native_tested':False}
        if executable:
            target,_,_=plan(executable);data['target']=str(target)
        return {'ok':True,'data':data}
    except Exception as exc:return failure('installation',exc)


@contextmanager
def install_lock():
    root=runtime_directory();protect_directory(root)
    path=safe_path(root/'installation.lock')
    try:
        handle=path.open('x',encoding='utf-8')
    except FileExistsError:
        raise ValueError('Another installation operation holds installation.lock; if interrupted, inspect and remove only that stale lock before retrying')
    try:
        with handle:handle.write(str(os.getpid()))
        yield
    finally:path.unlink()


def install(confirmed=False,executable=None):
    if not confirmed:return _install(False,executable)
    try:
        with install_lock():return _install(True,executable)
    except Exception as exc:return failure('installation',exc)


def _install(confirmed=False,executable=None):
    try:
        target,current,selected=plan(executable)
        if not confirmed:return {'ok':True,'data':{'preview':True,'target':str(target),'updates_existing':current is not None,'requires_restart':True,'may_require_windows_admin':True,'preference_changed':False}}
        root=runtime_directory();protect_directory(root)
        installation_id=uuid.uuid4().hex
        config={'root':str(root),'profile':os.environ['LOCALAPPDATA'],'installation_id':installation_id}
        text='(function(){var cfg='+json.dumps(config,ensure_ascii=True)+';if(String($.getenv("LOCALAPPDATA")).replace(/\\\\/g,"/").toLowerCase()!==cfg.profile.replace(/\\\\/g,"/").toLowerCase())return;\n'+SOURCE+'\nif($.global.BubbleAEBridge){$.global.BubbleAEBridge.stop();}$.global.BubbleAEBridge=createBubbleAEBridge(cfg);$.global.BubbleAEBridge.start();})();\n'
        raw=text.encode('utf-8')
        # Stage both outputs before either commit. Restore exact previous bytes
        # if receipt publication fails after the Startup replacement.
        temp=safe_path(target.with_suffix('.bubble-tmp'))
        rp=safe_path(root/'receipt.json');rt=safe_path(root/'receipt.tmp')
        if temp.exists() or rt.exists():raise ValueError('Pending temporary install/receipt exists; inspect before proceeding')
        old_raw=target.read_bytes() if target.exists() else None
        old_receipt=rp.read_bytes() if rp.exists() else None
        r={'schema':1,'version':'0.3.0','installation_id':installation_id,'profile':os.environ['LOCALAPPDATA'],'target':str(target),'executable':selected['executable'],'sha256':hashlib.sha256(raw).hexdigest(),'enabled':True}
        replaced=False
        try:
            with temp.open('xb') as f:f.write(raw)
            with rt.open('x',encoding='utf-8') as f:json.dump(r,f)
            os.replace(temp,target)
            replaced=True
            os.replace(rt,rp)
        except Exception:
            if replaced:
                if old_raw is None:target.unlink()
                else:target.write_bytes(old_raw)
                if old_receipt is None:
                    if rp.exists():rp.unlink()
                else:rp.write_bytes(old_receipt)
            raise
        finally:
            if temp.exists():temp.unlink()
            if rt.exists():rt.unlink()
        return {'ok':True,'data':{'installed':True,'target':str(target),'requires_restart':True,'preference_changed':False,'native_tested':False}}
    except PermissionError as exc:return failure('permission_denied','Windows denied the exact Startup path. Administrator write permission may be required; no elevation or preference change was attempted. '+str(exc))
    except Exception as exc:return failure('installation',exc)


def uninstall(confirmed=False):
    if not confirmed:return _uninstall(False)
    try:
        with install_lock():return _uninstall(True)
    except Exception as exc:return failure('uninstall',exc)


def _uninstall(confirmed=False):
    try:
        r=receipt()
        if not r:return {'ok':True,'data':{'installed':False,'removed_files':[],'runtime_cleanup':cleanup_runtime() if confirmed else None}}
        target=safe_path(Path(r['target']))
        # Constrain receipt targets to this user's deterministic Startup filename.
        suffix=hashlib.sha256(os.environ['LOCALAPPDATA'].casefold().encode()).hexdigest()[:12]
        exe=Path(r['executable'])
        expected=exe.parent/'Scripts'/'Startup'/('BubbleAfterEffects-'+suffix+'.jsx')
        if target!=expected or exe.name.lower()!='afterfx.exe' or exe.parent.name.lower()!='support files':raise ValueError('Receipt target is outside managed Startup scope')
        modified=not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=r['sha256']
        if not confirmed:return {'ok':True,'data':{'preview':True,'target':str(target),'preference_changed':False}}
        if modified:
            safe_path(runtime_directory()/'receipt.json').unlink()
            return {'ok':True,'data':{'removed_files':[],'connection_revoked':True,'preserved_modified_startup':str(target),'runtime_cleanup':cleanup_runtime(),'note':'Modified or missing Startup file was preserved; no new command will start after the next pump check. Already running commands may finish.'}}
        target.unlink()
        safe_path(runtime_directory()/'receipt.json').unlink()
        return {'ok':True,'data':{'removed_files':[str(target)],'loaded_bridge_stops_on_next_tick':True,'runtime_cleanup':cleanup_runtime(),'preference_changed':False}}
    except Exception as exc:return failure('uninstall',exc)
