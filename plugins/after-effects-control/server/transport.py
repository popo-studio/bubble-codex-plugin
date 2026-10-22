"""Authenticated per-instance local file IPC. No application launch or automatic retries."""
import json
import ntpath
from pathlib import Path
import secrets
import threading
import time
import uuid
from privacy import runtime_directory,safe_path
from installation import receipt

_lock=threading.Lock()
_server_id=uuid.uuid4().hex
_tokens={}

def failure(code,message):return {'ok':False,'error':{'code':code,'message':str(message)}}

def discover(project=None,private=False):
    rows=[];root=safe_path(runtime_directory()/'hosts')
    owner=receipt()
    if not owner or not owner.get('enabled') or not root.exists():return {'ok':True,'data':[],'selection':{'status':'none','matches':[],'selected':None}}
    candidates=[];budget_end=time.monotonic()+.25
    for index,folder in enumerate(root.iterdir()):
        if index>=10000:raise ValueError('Host discovery exceeds 10000 directory limit; inspect stale runtime data')
        if len(folder.name)!=32 or any(c not in '0123456789abcdef' for c in folder.name):continue
        try:
            # Metadata-only filtering avoids walking every ancestor for empty
            # stale directories. Validate links before reading any candidate.
            p=folder/'heartbeat.json'
            try:modified=p.stat().st_mtime
            except FileNotFoundError:
                pending=folder/'heartbeat.json.tmp'
                modified=pending.stat().st_mtime
            if modified<time.time()-20:continue
            candidates.append((modified,folder,p))
        except (OSError,ValueError):continue
    candidates.sort(key=lambda row:row[0],reverse=True)
    for _,folder,p in candidates[:256]:
        try:
            safe_path(p)
            r=None
            for attempt in range(3):
                try:
                    if p.stat().st_size>65536:break
                    r=json.loads(p.read_text(encoding='utf-8-sig'));break
                except FileNotFoundError:
                    if time.monotonic()>=budget_end:break
                    time.sleep(.02)
            if not isinstance(r,dict):continue
            project_info=r.get('project')
            if not isinstance(project_info,dict) or not isinstance(project_info.get('name'),str) or (project_info.get('path') is not None and not isinstance(project_info.get('path'),str)):continue
            if r.get('installation_id')!=owner['installation_id'] or r.get('bridge_version')!='0.3.0':continue
            if r.get('schema')!=1 or r.get('session_id')!=folder.name or not isinstance(r.get('expires_at'),(int,float)) or not time.time()*1000<r['expires_at']<=time.time()*1000+20000 or not str(r.get('version','')).startswith('26.') or not isinstance(r.get('token'),str) or len(r['token'])!=64:continue
            if not private:r.pop('token',None)
            rows.append(r)
        except (OSError,ValueError,TypeError):continue
    matches=[]
    for r in rows:
        p=r.get('project') or {};query=project.casefold() if isinstance(project,str) else None
        if query and (query in [str(p.get('name','')).casefold(),ntpath.splitext(str(p.get('name','')))[0].casefold()] or ntpath.normcase(ntpath.normpath(query))==ntpath.normcase(ntpath.normpath(p.get('path') or ''))):matches.append(r['session_id'])
    status='unspecified' if not project else 'unique' if len(matches)==1 else 'ambiguous' if matches else 'none'
    return {'ok':True,'data':rows,'selection':{'status':status,'matches':matches,'selected':matches[0] if status=='unique' else None}}

def call(operation,session_id,expected_project_state=None,timeout=20,**args):
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 1<=timeout<=120:return failure('invalid_request','timeout must be 1–120 seconds')
    with _lock:
        paths=[]
        try:
            selected=next((r for r in discover(private=True)['data'] if r['session_id']==session_id),None)
            if not selected:return failure('session','Selected AE instance is no longer connected; no fallback')
            token=_tokens.setdefault(session_id,secrets.token_hex(32))
            root=safe_path(runtime_directory()/'hosts'/session_id)
            request_id=uuid.uuid4().hex
            request=safe_path(root/'requests'/(request_id+'.json'));temp=safe_path(root/'requests'/(request_id+'.tmp'));response=safe_path(root/'results'/(request_id+'.json'))
            paths=[temp,request,response]
            q=dict(operation=operation,session_id=session_id,host_token=selected['token'],request_id=request_id,server_id=_server_id,token=token,expires_at=int((time.time()+timeout)*1000),expected_project_state=expected_project_state,args=args)
            raw=json.dumps(q,ensure_ascii=True,allow_nan=False)
            if len(raw)>1048576:return failure('size','Request exceeds 1 MiB')
            with temp.open('x',encoding='utf-8') as f:f.write(raw)
            temp.rename(request)
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                if response.exists():
                    if response.stat().st_size>8*1024*1024:return failure('size','Oversized response; operation may have completed, do not retry')
                    try:r=json.loads(response.read_text(encoding='utf-8-sig'))
                    except (ValueError,PermissionError):time.sleep(.05);continue
                    if r.get('request_id')!=request_id:return failure('response','Mismatched request identity')
                    r.pop('request_id',None);return r
                time.sleep(.05)
            return failure('timeout_outcome_unknown','No verified reply before deadline. Operation may have partially completed. Inspect selected instance; never retry automatically.')
        except Exception as exc:return failure('connection',exc)
        finally:
            for p in paths:
                try:
                    safe_path(p)
                    if p.exists():p.unlink()
                except OSError:pass
