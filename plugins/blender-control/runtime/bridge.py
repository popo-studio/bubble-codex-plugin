"""Run start() from Blender's Python Script Editor. No third-party dependencies."""
import atexit
import queue
import contextlib
import glob
import hmac
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import socketserver
import threading
import time
import traceback


# Load the complete managed payload once, before either source can be removed.
import importlib.util as _importlib_util
_operations_spec = _importlib_util.spec_from_file_location('_bubble_blender_operations', Path(__file__).with_name('operations.py'))
_operations = _importlib_util.module_from_spec(_operations_spec)
_operations_spec.loader.exec_module(_operations)
_privacy_spec=_importlib_util.spec_from_file_location('_bubble_blender_privacy',Path(__file__).with_name('privacy.py'))
_privacy=_importlib_util.module_from_spec(_privacy_spec);_privacy_spec.loader.exec_module(_privacy)
STRUCTURED_OPERATIONS = {'structured_' + value for value in ('state','file','query','create','edit','selection','material','camera','light','timeline','render_settings','assets')}

PROTOCOL = 1
MAX_MESSAGE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
_bridge = None
_script_globals = {"__name__": "__bubble_blender_script__"}


def session_directory():
    return Path(os.environ.get("BUBBLE_BLENDER_SESSION_DIR", str(Path.home() / ".bubble-blender" / "sessions")))


def failure(code, message, **details):
    return {"ok": False, "error": {"code": code, "message": message, **details}}


class LimitedOutput(io.StringIO):
    def write(self, value):
        available = max(0, MAX_OUTPUT - self.tell())
        super().write(value[:available])
        return len(value)


def _serializable(value):
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)[:MAX_OUTPUT]


def scene_info(bpy):
    return {'path':bpy.data.filepath,'modified':bpy.data.is_dirty,'blender_version':bpy.app.version_string,'selection':[o.name for o in bpy.context.selected_objects],'frame':bpy.context.scene.frame_current}


def dispatch(operation, arguments):
    import bpy
    if tuple(bpy.app.version[:2]) < (4,5):raise ValueError('Blender 4.5 or later required')
    if operation in STRUCTURED_OPERATIONS:return _operations.dispatch(operation.removeprefix('structured_'),arguments)
    if operation=='status':return {'bridge_version':'0.1.0','pid':os.getpid(),'blender_version':bpy.app.version_string,'protocol':PROTOCOL}
    if operation=='scene_info':return scene_info(bpy)
    if operation=='inspect_scene':return _operations.dispatch('assets',{})
    if operation!='execute_python':raise ValueError('Unknown operation')
    _operations.guard(bpy,arguments)
    code=arguments.get('code')
    if not isinstance(code,str) or not code.strip():raise ValueError('Nonempty authorized code required')
    output,errors=LimitedOutput(),LimitedOutput()
    with contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
        scope={'bpy':bpy,'__name__':'__bubble_blender_script__'}
        exec(compile(code,'<Bubble Blender>','exec'),scope,scope)
    return {'result':_serializable(scope.get('result')),'stdout':output.getvalue(),'stderr':errors.getvalue()}


class Bridge(socketserver.TCPServer):
    allow_reuse_address = False

    def __init__(self, dispatch_fn, schedule_fn):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token = secrets.token_urlsafe(32)
        self.dispatch_fn, self.schedule_fn = dispatch_fn, schedule_fn
        self.closed = threading.Event()
        self.session_file = None

    def invoke(self, request):
        if not isinstance(request, dict):
            return failure("invalid_request", "Expected a JSON object")
        token = request.get("token")
        if not isinstance(token, str) or not hmac.compare_digest(token.encode("utf-8", errors="surrogatepass"), self.token.encode("ascii")):
            return failure("unauthorized", "Invalid session token")
        if request.get("protocol") != PROTOCOL:
            return failure("protocol_mismatch", "Unsupported protocol version")
        operation = request.get("operation")
        if not isinstance(operation, str) or operation not in STRUCTURED_OPERATIONS | {"status", "scene_info", "inspect_scene", "execute_python"}:
            return failure("invalid_operation", "Unsupported operation")
        arguments = request.get("arguments", {})
        timeout = request.get("timeout", 30)
        if not isinstance(arguments, dict) or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            return failure("invalid_request", "arguments must be an object; timeout must be in (0, 120]")
        expires_at = request.get("expires_at")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) or not math.isfinite(expires_at):
            return failure("invalid_request", "A finite expires_at Unix timestamp is required")
        # The client deadline includes time waiting in the OS accept backlog.
        # Never start a request merely because a previous request finally finished.
        timeout = min(timeout, expires_at - time.time())
        if timeout <= 0:
            return failure("queue_timeout", "Request expired before dispatch; no operation was started.", execution_started=False)
        completed, lock = threading.Event(), threading.Lock()
        state = {"cancelled": False, "started": False}
        deadline = time.monotonic() + timeout

        def run():
            with lock:
                if state["cancelled"] or self.closed.is_set() or time.monotonic() >= deadline:
                    return
                state["started"] = True
            try:
                result = self.dispatch_fn(operation, arguments)
                state["response"] = result if isinstance(result, dict) and result.get("ok") is False else {"ok": True, "data": result}
            except Exception:
                state["response"] = failure("operation_error", "Blender operation failed", traceback=traceback.format_exc()[-MAX_OUTPUT:])
            finally:
                completed.set()

        try:
            self.schedule_fn(run)
        except Exception:
            with lock:
                state["cancelled"] = True
            return failure("scheduling_error", "Could not schedule Blender work. Do not retry automatically.", execution_started=state["started"])
        if not completed.wait(timeout):
            with lock:
                state["cancelled"] = True
                started = state["started"]
            return failure("execution_timeout" if started else "queue_timeout", "Do not retry automatically. Execution may still be running." if started else "Blender did not become idle; queued operation was cancelled.", execution_started=started)
        return state["response"]


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            line = self.rfile.readline(MAX_MESSAGE + 1)
            if len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
                response = failure("invalid_request", "Request missing newline or exceeds 1 MiB")
            else:
                response = self.server.invoke(json.loads(line))
            encoded = json.dumps(response, ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
            if len(encoded) > MAX_MESSAGE:
                encoded = json.dumps(failure("response_too_large", "Response exceeds 1 MiB. Operation may have completed; do not retry automatically.")).encode() + b"\n"
            self.wfile.write(encoded)
        except (ValueError, OSError):
            # Malformed/disconnected clients cannot terminate the listener.
            try:
                self.wfile.write(json.dumps(failure("invalid_request", "Malformed request or connection timeout")).encode() + b"\n")
            except OSError:
                pass


def start():
    """Start a loopback bridge in interactive Blender; returns public session metadata."""
    global _bridge
    if _bridge is not None:
        return {"pid": os.getpid(), "port": _bridge.server_address[1], "already_running": True}
    import bpy
    if tuple(bpy.app.version[:2]) < (4,5):raise RuntimeError('Blender 4.5 or later required')
    _operations.begin_session()
    pending = queue.Queue(maxsize=64)
    def drain():
        if bridge.closed.is_set():return None
        try:pending.get_nowait()()
        except queue.Empty:pass
        return 0.05
    bridge=Bridge(dispatch,pending.put_nowait)
    bridge.drain=drain
    try:
        bpy.app.timers.register(drain,first_interval=0.2,persistent=True)
    except Exception:
        bridge.server_close()
        raise
    bridge.remove_callback=lambda: bpy.app.timers.unregister(drain) if bpy.app.timers.is_registered(drain) else None
    temporary = None
    try:
        directory = session_directory()
        _privacy.protect_directory(directory)
        session_file = directory / (str(os.getpid()) + ".json")
        metadata = {"protocol": PROTOCOL, "pid": os.getpid(), "host": "127.0.0.1", "port": bridge.server_address[1], "blender_version": bpy.app.version_string, "created_at": time.time()}
        temporary = session_file.with_suffix("." + secrets.token_hex(8) + ".tmp")
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**metadata, "token": bridge.token}, handle)
        os.replace(str(temporary), str(session_file))
    except Exception:
        bridge.server_close()
        if hasattr(bridge, "remove_callback"):
            bridge.remove_callback()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    bridge.session_file = session_file
    _bridge = bridge
    atexit.register(stop)
    threading.Thread(target=bridge.serve_forever, name="BubbleBlenderBridge", daemon=True).start()
    return metadata


def stop():
    """Stop listening, cancel queued work, and remove this process's discovery file."""
    global _bridge
    bridge, _bridge = _bridge, None
    if bridge is None:
        return
    bridge.closed.set()
    if hasattr(bridge, "remove_callback"):
        try:
            bridge.remove_callback()
        except Exception:
            pass  # Host may already have removed callbacks during shutdown.
    # Shutdown in a worker: never block Blender's UI waiting for pending main-thread work.
    def shutdown():
        bridge.shutdown()
        bridge.server_close()
    threading.Thread(target=shutdown, name="BubbleBlenderStop", daemon=True).start()
    if bridge.session_file:
        bridge.session_file.unlink(missing_ok=True)
