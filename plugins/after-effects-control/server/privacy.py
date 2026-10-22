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

PLUGIN_ID = "com.popostudio.bubble.aftereffects"
INTERVAL = 3
TTL = 12

def runtime_directory():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise ValueError("LOCALAPPDATA must be an absolute per-user directory")
    return Path(base) / "Bubble/Codex/after-effects"

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
