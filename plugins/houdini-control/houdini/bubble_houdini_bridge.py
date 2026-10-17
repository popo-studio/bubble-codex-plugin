"""Run start() from Houdini's Python Script Editor. No third-party dependencies."""
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

PROTOCOL = 1
MAX_MESSAGE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
_bridge = None
_script_globals = {"__name__": "__bubble_houdini_script__"}


def session_directory():
    return Path(os.environ.get("BUBBLE_HOUDINI_SESSION_DIR", str(Path.home() / ".bubble-houdini" / "sessions")))


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


def scene_info(hou):
    return {"path": "" if hou.hipFile.isNewFile() else hou.hipFile.path(),
            "modified": bool(hou.hipFile.hasUnsavedChanges()),
            "houdini_version": hou.applicationVersionString(),
            "project": hou.getenv("JOB") or hou.getenv("HIP") or "",
            "selection": [node.path() for node in hou.selectedNodes()], "frame": hou.frame()}


def inspect_scene(hou):
    info = scene_info(hou)
    references, warnings = [], []
    for parm, path in hou.fileReferences():
        try:
            item = {"parameter": parm.path() if parm is not None else None, "path": path}
            # Backticks execute HScript expressions; don't evaluate them during checks.
            if not path or "`" in path or path.startswith(("op:", "opdef:", "oplib:", "http:", "https:")) or "$FF" in path or "${FF}" in path:
                item.update(status="unverified", reason="Empty, embedded expression, non-file reference or fractional frame token")
            else:
                def frame_token(match):
                    width = match.group(1) or match.group(2)
                    if not width:
                        return "<f>"
                    if len(width) > 2 or not 1 <= int(width) <= 16:
                        raise ValueError("Unsupported frame padding; expected 1..16 digits")
                    return "#" * int(width)
                tokenized = re.sub(r"\$\{F(\d*)\}|\$F(\d*)(?![A-Za-z_0-9])", frame_token, path)
                resolved = hou.expandString(tokenized)
                # An unknown variable stays unresolved; don't report it as a missing file.
                if "$" in resolved:
                    item.update(status="unverified", reason="Unresolved environment variable")
                else:
                    item.update(path_status(resolved, hou.getenv("HIP") or os.getcwd()), status="checked")
            references.append(item)
        except Exception as error:
            warnings.append({"path": path, "message": str(error)})
    return {"scene": info, "references": references,
            "missing_path_candidates": [r for r in references if r.get("exists") is False],
            "unverified": [r for r in references if r["status"] == "unverified"], "warnings": warnings,
            "coverage": "hou.fileReferences() paths including asset libraries. Parameters can represent future output files, so missing candidates need review; this is not a definitive missing-input audit. Frame/UDIM checks require any matching frame/tile, not every frame. Embedded expressions and non-file references are not evaluated."}



def path_status(path, project="", sequence=False):
    """Check literal paths and common Houdini UDIM/UV/frame patterns without edits."""
    expanded = os.path.expandvars(path) if path else ""
    if expanded and not os.path.isabs(expanded):
        expanded = os.path.join(project, expanded)
    if not expanded:
        return {"resolved_path": "", "exists": False, "pattern": False}
    source = os.path.normcase(os.path.normpath(expanded))
    tokens = re.compile(r"<UDIM>|<UVTILE>|<[uv]>|<f(?:rame)?>|#+|%0?\d*d", re.I)
    if sequence and not tokens.search(source):
        source = re.sub(r"\d+(?=\.[^.\/\\]+$)", "<f>", source)
    matches = list(tokens.finditer(source))
    is_pattern = bool(matches)
    glob_parts, regex_parts, offset = [], [], 0
    for match in matches:
        literal, token = source[offset:match.start()], match.group().lower()
        glob_parts.extend([glob.escape(literal), "*"])
        if token == "<udim>":
            numeric = r"[0-9]{4}"
        elif token == "<uvtile>":
            numeric = r"u[0-9]+_v[0-9]+"
        elif token.startswith("#"):
            numeric = r"[0-9]{%d}" % len(token)
        elif token.startswith("%") and token[1:-1].lstrip("0"):
            numeric = r"[0-9]{%d}" % int(token[1:-1])
        else:
            numeric = r"[0-9]+"
        regex_parts.extend([re.escape(literal), numeric])
        offset = match.end()
    glob_parts.append(glob.escape(source[offset:]))
    regex_parts.append(re.escape(source[offset:]))
    expected = re.compile("".join(regex_parts))
    exists = any(os.path.isfile(p) and expected.fullmatch(os.path.normcase(os.path.normpath(p))) for p in glob.iglob("".join(glob_parts))) if is_pattern else os.path.isfile(expanded)
    return {"resolved_path": expanded, "exists": exists, "pattern": is_pattern}


def dispatch(operation, arguments):
    """Called only on the host main thread."""
    import hou
    if operation == "status":
        return {"pid": os.getpid(), "houdini_version": hou.applicationVersionString(), "protocol": PROTOCOL}
    if operation == "scene_info":
        return scene_info(hou)
    if operation == "inspect_scene":
        return inspect_scene(hou)
    if operation != "execute_python":
        raise ValueError("Unsupported operation: " + operation)
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")
    output, errors = LimitedOutput(), LimitedOutput()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            _script_globals.update({"hou": hou})
            _script_globals.pop("result", None)
            exec(compile(code, "<bubble-houdini>", "exec"), _script_globals)
            return {"result": _serializable(_script_globals.get("result")), "stdout": output.getvalue(), "stderr": errors.getvalue()}
        except Exception:
            return failure("script_error", "Script failed; earlier changes may have occurred.", traceback=traceback.format_exc()[-MAX_OUTPUT:], stdout=output.getvalue(), stderr=errors.getvalue())


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
        if not isinstance(operation, str) or operation not in {"status", "scene_info", "inspect_scene", "execute_python"}:
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
                state["response"] = failure("operation_error", "Houdini operation failed", traceback=traceback.format_exc()[-MAX_OUTPUT:])
            finally:
                completed.set()

        try:
            self.schedule_fn(run)
        except Exception:
            with lock:
                state["cancelled"] = True
            return failure("scheduling_error", "Could not schedule Houdini work. Do not retry automatically.", execution_started=state["started"])
        if not completed.wait(timeout):
            with lock:
                state["cancelled"] = True
                started = state["started"]
            return failure("execution_timeout" if started else "queue_timeout", "Do not retry automatically. Execution may still be running." if started else "Houdini did not become idle; queued operation was cancelled.", execution_started=started)
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
    """Start a loopback bridge in interactive Houdini; returns public session metadata."""
    global _bridge
    if _bridge is not None:
        return {"pid": os.getpid(), "port": _bridge.server_address[1], "already_running": True}
    import hou
    if not hou.isUIAvailable():
        raise RuntimeError("Bridge requires interactive Houdini")
    import sys
    if not hou.applicationVersionString().startswith("20.5.") or sys.version_info[:2] != (3, 11):
        raise RuntimeError("This bridge release supports Houdini 20.5 with Python 3.11 only")
    pending = queue.Queue(maxsize=64)
    def drain():
        try:
            pending.get_nowait()()
        except queue.Empty:
            pass
    bridge = Bridge(dispatch, pending.put_nowait)
    try:
        hou.ui.addEventLoopCallback(drain)
    except Exception:
        bridge.server_close()
        raise
    bridge.remove_callback = lambda: hou.ui.removeEventLoopCallback(drain)
    temporary = None
    try:
        directory = session_directory()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        session_file = directory / (str(os.getpid()) + ".json")
        metadata = {"protocol": PROTOCOL, "pid": os.getpid(), "host": "127.0.0.1", "port": bridge.server_address[1], "houdini_version": hou.applicationVersionString(), "created_at": time.time()}
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
    threading.Thread(target=bridge.serve_forever, name="BubbleHoudiniBridge", daemon=True).start()
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
    # Shutdown in a worker: never block Houdini's UI waiting for pending main-thread work.
    def shutdown():
        bridge.shutdown()
        bridge.server_close()
    threading.Thread(target=shutdown, name="BubbleHoudiniStop", daemon=True).start()
    if bridge.session_file:
        bridge.session_file.unlink(missing_ok=True)
