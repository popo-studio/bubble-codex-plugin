"""Run start() from Unreal Engine's Python Script Editor. No third-party dependencies."""
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

PROTOCOL = 1
MAX_MESSAGE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
_bridge = None
_script_globals = {"__name__": "__bubble_unreal_script__"}


def session_directory():
    return Path(os.environ.get("BUBBLE_UNREAL_SESSION_DIR", str(Path.home() / ".bubble-unreal" / "sessions")))


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
        if not isinstance(operation, str) or operation not in {"status", "scene_info", "inspect_scene", 'list_objects', 'inspect_object', 'object_action', 'scene_action', 'settings', "execute_python"}:
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
                state["response"] = failure("operation_error", "Unreal Engine operation failed", traceback=traceback.format_exc()[-MAX_OUTPUT:])
            finally:
                completed.set()

        try:
            self.schedule_fn(run)
        except Exception:
            with lock:
                state["cancelled"] = True
            return failure("scheduling_error", "Could not schedule Unreal Engine work. Do not retry automatically.", execution_started=state["started"])
        if not completed.wait(timeout):
            with lock:
                state["cancelled"] = True
                started = state["started"]
            return failure("execution_timeout" if started else "queue_timeout", "Do not retry automatically. Execution may still be running." if started else "Unreal Engine did not become idle; queued operation was cancelled.", execution_started=started)
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



# Host code is loaded by exact sibling path, never a generic import from sys.path.
import importlib.util
import sys
_host_spec = importlib.util.spec_from_file_location("_bubble_unreal_host", Path(__file__).with_name("host.py"))
_host = importlib.util.module_from_spec(_host_spec)
_host_spec.loader.exec_module(_host)


def dispatch(operation, arguments):
    if operation in {'scene_action', 'inspect_object', 'list_objects', 'object_action', 'settings'}:
        return _host.structured(operation, arguments)
    if operation == "status":
        return {"bridge_version": "0.3.0", "pid": os.getpid(), "protocol": PROTOCOL, "version": _host.scene_info()["unreal_version"]}
    if operation == "scene_info":
        return _host.scene_info()
    if operation == "inspect_scene":
        return _host.inspect_scene(arguments.get("package"))
    import unreal
    code = arguments.get("code")
    if operation not in ("execute_python",) or not isinstance(code, str) or not code.strip():
        raise ValueError("Unsupported operation or empty code")
    _host.ensure_script_allowed()
    output, errors = LimitedOutput(), LimitedOutput()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            if operation == "execute_python":
                _script_globals.update({"unreal": unreal})
                _script_globals.pop("result", None)
                exec(compile(code, "<bubble-unreal>", "exec"), _script_globals)
                result = _script_globals.get("result")
            else:
                result = None
            return {"result": _serializable(result), "stdout": output.getvalue(), "stderr": errors.getvalue()}
        except Exception:
            return failure("script_error", "Script failed; earlier changes may already exist. Do not retry automatically.", traceback=traceback.format_exc()[-MAX_OUTPUT:], stdout=output.getvalue(), stderr=errors.getvalue())


def start():
    global _bridge
    if _bridge is not None:
        return {"pid": os.getpid(), "port": _bridge.server_address[1], "already_running": True}
    schedule = _host.install_dispatcher(stop)
    bridge = None
    temporary = None
    try:
        bridge = Bridge(dispatch, schedule)
        info = _host.scene_info()
        directory = session_directory()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        session_file = directory / (str(os.getpid()) + ".json")
        metadata = {"protocol": PROTOCOL, "pid": os.getpid(), "host": "127.0.0.1",
                    "port": bridge.server_address[1], "unreal_version": info["unreal_version"], "created_at": time.time()}
        temporary = session_file.with_suffix("." + secrets.token_hex(8) + ".tmp")
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**metadata, "token": bridge.token}, handle)
        os.replace(str(temporary), str(session_file))
        bridge.session_file = session_file
        _bridge = bridge
        threading.Thread(target=bridge.serve_forever, name="BubbleunrealBridge", daemon=True).start()
        return metadata
    except Exception:
        _host.remove_dispatcher()
        if bridge is not None:
            bridge.server_close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def stop():
    global _bridge
    bridge, _bridge = _bridge, None
    if bridge is None:
        return
    bridge.closed.set()
    _host.remove_dispatcher()
    def shutdown():
        bridge.shutdown()
        bridge.server_close()
    threading.Thread(target=shutdown, name="BubbleunrealStop", daemon=True).start()
    if bridge.session_file:
        bridge.session_file.unlink(missing_ok=True)
