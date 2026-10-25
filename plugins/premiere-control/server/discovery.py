"""Current-user-only, expiring broker discovery. Never publish before protected ACL exists."""
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

PLUGIN_ID = "com.popostudio.bubble.premiere"
INTERVAL = 3
TTL = 12

def runtime_directory():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise ValueError("LOCALAPPDATA must be an absolute per-user directory")
    return Path(base) / "Bubble/Codex/premiere/discovery"

def safe_path(path):
    path = Path(path).absolute()
    for node in [path,*path.parents]:
        if node.is_symlink() or (node.exists() and getattr(node.stat(),"st_file_attributes",0)&0x400):
            raise ValueError("Refusing a discovery reparse point")
    return path

def protect_directory(path):
    safe_path(path)
    path.mkdir(parents=True,exist_ok=True)
    safe_path(path)
    if os.name != "nt":
        os.chmod(path,0o700)
        return
    # Absolute system executable prevents PATH substitution. No shell or visible process.
    whoami = Path(os.environ.get("SystemRoot","C:/Windows"))/"System32/whoami.exe"
    output = subprocess.check_output([str(whoami),"/user","/fo","csv","/nh"],
        creationflags=subprocess.CREATE_NO_WINDOW,timeout=5).decode("utf-8",errors="replace")
    match=re.search(r"S-1-(?:[0-9]+-)*[0-9]+",output)
    if not match: raise OSError("Cannot establish current user SID")
    sid=match.group()
    advapi=ctypes.WinDLL("advapi32",use_last_error=True)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    convert=advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
    convert.restype=ctypes.c_int
    apply=advapi.SetFileSecurityW
    apply.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_void_p];apply.restype=ctypes.c_int
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    descriptor=ctypes.c_void_p()
    # Protected DACL: only this user and SYSTEM; child files inherit these permissions.
    if not convert("D:P(A;OICI;FA;;;"+sid+")(A;OICI;FA;;;SY)",1,ctypes.byref(descriptor),None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not apply(str(path),0x80000004,descriptor): raise ctypes.WinError(ctypes.get_last_error())
    finally: kernel.LocalFree(descriptor)

def installation_enabled():
    from installation import _target, _safe, _owned
    try:
        owned=_owned(_safe(_target()))
        return bool(owned and owned.get("version")=="0.5.0")
    except (ValueError,OSError): return False

class Publisher:
    def __init__(self,port,token,directory=None,enabled=None):
        self.directory=Path(directory) if directory is not None else runtime_directory()
        self.identifier=str(uuid.uuid4())
        self.path=self.directory/(self.identifier+".json")
        self.port=port;self.token=token;self.enabled=enabled or installation_enabled
        self.stop=threading.Event();self.thread=None;self.error=None
    def publish(self):
        if not self.enabled():
            self.remove();return False
        protect_directory(self.directory)
        safe_path(self.path)
        record={"schema":1,"plugin_id":PLUGIN_ID,"broker_id":self.identifier,
            "pid":os.getpid(),"port":self.port,"token":self.token,"expires_at":time.time()+TTL}
        temp=self.path.with_suffix(".tmp")
        safe_path(temp)
        # Exclusive create and inherited private DACL; atomic replacement publishes a complete record.
        created = False
        try:
            with temp.open("x",encoding="utf-8") as file:
                created = True
                json.dump(record,file)
            os.replace(temp,self.path)
        finally:
            if created and temp.exists():temp.unlink()
        self.error=None
        return True
    def remove(self):
        safe_path(self.path)
        if self.path.exists(): self.path.unlink()
    def start(self):
        if self.thread is not None:return
        def run():
            while not self.stop.is_set():
                try:self.publish()
                except (OSError,ValueError,subprocess.SubprocessError):
                    self.error="Automatic discovery unavailable; inspect installation and current-user directory permissions"
                    try:self.remove()
                    except (OSError,ValueError):pass
                self.stop.wait(INTERVAL)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=7)
        try:self.remove()
        except (OSError,ValueError):pass

def cleanup_records():
    """Remove only bounded owned records, never another application's files or unknown files."""
    directory=safe_path(runtime_directory())
    if not directory.exists():return
    for path in list(directory.glob("*.json"))[:128]:
        safe_path(path)
        if path.stat().st_size>4096:continue
        try:
            record=json.loads(path.read_text(encoding="utf-8"))
            if record.get("plugin_id")==PLUGIN_ID and str(uuid.UUID(record.get("broker_id","")))+".json"==path.name:
                path.unlink()
        except (ValueError,TypeError,OSError):continue
