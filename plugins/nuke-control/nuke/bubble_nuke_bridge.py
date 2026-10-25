"""Run start() from Nuke's Python Script Editor. No third-party dependencies."""
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
_operations_spec = _importlib_util.spec_from_file_location('_bubble_nuke_operations', Path(__file__).with_name('operations.py'))
_operations = _importlib_util.module_from_spec(_operations_spec)
_operations_spec.loader.exec_module(_operations)
STRUCTURED_OPERATIONS = {'structured_' + value for value in ('state','file','query','create','edit','selection','attribute','connections','timeline','keyframes','transfer','project')}

PROTOCOL = 1
MAX_MESSAGE = 1024 * 1024
MAX_OUTPUT = 128 * 1024
_bridge = None
_script_globals = {"__name__": "__bubble_nuke_script__"}


def session_directory():
    return Path(os.environ.get("BUBBLE_NUKE_SESSION_DIR", str(Path.home() / ".bubble-nuke" / "sessions")))


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


def scene_info(nuke):
    root = nuke.root()
    name = root.name()
    project = root.knob("project_directory")
    return {"path": "" if name in ("", "Root") else name,
            "modified": bool(nuke.modified()), "nuke_version": nuke.NUKE_VERSION_STRING,
            "project": project.value() if project else "",
            "selection": [node.fullName() for node in nuke.selectedNodes()],
            "frame": nuke.frame(), "node_count": len(nuke.allNodes(recurseGroups=True))}


def inspect_scene(nuke):
    info = scene_info(nuke)
    project = info["project"] or os.path.dirname(info["path"]) or os.getcwd()
    references, warnings = [], []
    for node in nuke.allNodes(recurseGroups=True):
        if node.Class() not in ("Read", "DeepRead", "ReadGeo", "ReadGeo2", "Camera2", "Axis2"):
            continue
        knob = node.knob("file")
        if knob is None:
            continue
        enabled = node.knob("read_from_file")
        if enabled is not None and not enabled.value():
            continue
        try:
            path = knob.value()
            item = {"node": node.fullName(), "class": node.Class(), "path": path}
            # Never evaluate embedded Tcl/Python from an asset string during an audit.
            if not isinstance(path, str) or any(c in path or c in project for c in ("[", "]", "`")) or "://" in path:
                item.update(status="unverified", reason="Expression or non-local path; not evaluated")
            else:
                item.update(path_status(path, project), status="checked")
            references.append(item)
        except Exception as error:
            warnings.append({"node": node.fullName(), "message": str(error)})
    return {"scene": info, "references": references,
            "missing_files": [r for r in references if r.get("exists") is False],
            "unverified": [r for r in references if r["status"] == "unverified"], "warnings": warnings,
            "coverage": "Read, DeepRead, ReadGeo/ReadGeo2 and enabled Camera2/Axis2 file inputs. Expressions and remote paths are not evaluated. Sequence/UDIM existence means any matching frame/tile, not full coverage. Write outputs and renderer/plugin assets are excluded."}



def path_status(path, project="", sequence=False):
    """Check literal paths and common Nuke UDIM/UV/frame patterns without edits."""
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
    printf_tokens = []
    for match in matches:
        literal, token = source[offset:match.start()], match.group().lower()
        glob_parts.extend([glob.escape(literal), "*"])
        if token == "<udim>":
            numeric = r"[0-9]{4}"
        elif token == "<uvtile>":
            numeric = r"u[0-9]+_v[0-9]+"
        elif token.startswith("#"):
            numeric = r"[0-9]{%d}" % len(token)
        elif token.startswith("%"):
            # printf width is a minimum and includes a possible minus sign.
            # Validate the captured value against formatting below, so shorter
            # unpadded names and over-padded small values do not match.
            name = "printf_%d" % len(printf_tokens)
            printf_tokens.append((name, token))
            numeric = r"(?P<%s> *-?[0-9]+)" % name
        else:
            numeric = r"[0-9]+"
        regex_parts.extend([re.escape(literal), numeric])
        offset = match.end()
    glob_parts.append(glob.escape(source[offset:]))
    regex_parts.append(re.escape(source[offset:]))
    expected = re.compile("".join(regex_parts))
    def matches_pattern(candidate):
        match = expected.fullmatch(os.path.normcase(os.path.normpath(candidate)))
        if match is None or not os.path.isfile(candidate):
            return False
        for name, token in printf_tokens:
            value = match.group(name)
            width = token[1:-1].lstrip("0") or "0"
            size = str(len(value))
            # Scene paths are input: never allocate their requested padding
            # before proving it can fit this actual candidate filename.
            if len(width) > len(size) or (len(width) == len(size) and width > size):
                return False
            if token % int(value) != value:
                return False
        return True
    exists = any(matches_pattern(p) for p in glob.iglob("".join(glob_parts))) if is_pattern else os.path.isfile(expanded)
    return {"resolved_path": expanded, "exists": exists, "pattern": is_pattern}


def dispatch(operation, arguments):
    if operation in STRUCTURED_OPERATIONS:
        return _operations.dispatch(operation.removeprefix("structured_"), arguments)
    """Called only on the host main thread."""
    import nuke
    if operation == "status":
        return {"bridge_version": "0.3.0", "pid": os.getpid(), "nuke_version": nuke.NUKE_VERSION_STRING, "protocol": PROTOCOL}
    if operation == "scene_info":
        return scene_info(nuke)
    if operation == "inspect_scene":
        return inspect_scene(nuke)
    if operation != "execute_python":
        raise ValueError("Unsupported operation: " + operation)
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")
    output, errors = LimitedOutput(), LimitedOutput()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            _script_globals.update({"nuke": nuke})
            _script_globals.pop("result", None)
            exec(compile(code, "<bubble-nuke>", "exec"), _script_globals)
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
                state["response"] = failure("operation_error", "Nuke operation failed", traceback=traceback.format_exc()[-MAX_OUTPUT:])
            finally:
                completed.set()

        try:
            self.schedule_fn(run)
        except Exception:
            with lock:
                state["cancelled"] = True
            return failure("scheduling_error", "Could not schedule Nuke work. Do not retry automatically.", execution_started=state["started"])
        if not completed.wait(timeout):
            with lock:
                state["cancelled"] = True
                started = state["started"]
            return failure("execution_timeout" if started else "queue_timeout", "Do not retry automatically. Execution may still be running." if started else "Nuke did not become idle; queued operation was cancelled.", execution_started=started)
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
    """Start a loopback bridge in interactive Nuke; returns public session metadata."""
    global _bridge
    if _bridge is not None:
        return {"pid": os.getpid(), "port": _bridge.server_address[1], "already_running": True}
    import nuke
    if not nuke.GUI:
        raise RuntimeError("Bridge requires interactive Nuke")
    if not nuke.NUKE_VERSION_STRING.startswith("15.1v"):
        raise RuntimeError("This bridge release supports Nuke 15.1 only")
    _operations.new_session()
    bridge = Bridge(dispatch, nuke.executeInMainThread)
    temporary = None
    try:
        directory = session_directory()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        session_file = directory / (str(os.getpid()) + ".json")
        metadata = {"protocol": PROTOCOL, "pid": os.getpid(), "host": "127.0.0.1", "port": bridge.server_address[1], "nuke_version": nuke.NUKE_VERSION_STRING, "created_at": time.time()}
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
    threading.Thread(target=bridge.serve_forever, name="BubbleNukeBridge", daemon=True).start()
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
    # Shutdown in a worker: never block Nuke's UI waiting for pending main-thread work.
    def shutdown():
        bridge.shutdown()
        bridge.server_close()
    threading.Thread(target=shutdown, name="BubbleNukeStop", daemon=True).start()
    if bridge.session_file:
        bridge.session_file.unlink(missing_ok=True)
