"""Bounded local bridge client. Never retry a request whose execution is uncertain."""
import json
import os
from pathlib import Path
import socket
import time

MAX_MESSAGE = 1024 * 1024


def failure(code, message, **details):
    return {"ok": False, "error": {"code": code, "message": message, **details}}


def session_directory():
    return Path(os.environ.get("BUBBLE_BLENDER_SESSION_DIR", str(Path.home() / ".bubble-blender" / "sessions")))


def sessions():
    found = []
    for path in sorted(session_directory().glob("*.json")):
        try:
            if path.stat().st_size > 16384:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if (value.get("protocol") != 1 or value.get("host") != "127.0.0.1"
                    or type(value.get("port")) is not int or not 0 < value["port"] < 65536
                    or type(value.get("pid")) is not int or value["pid"] <= 0
                    or path.stem != str(value["pid"])
                    or not isinstance(value.get("token"), str) or len(value["token"]) < 32):
                continue
            found.append(value)
        except (OSError, ValueError, AttributeError):
            continue
    return found


def list_sessions():
    return {"ok": True, "data": [{k: v for k, v in item.items() if k != "token"} for item in sessions()], "note": "Discovery files can be stale after a crash. Use blender_status(pid) to check connectivity."}


def request(operation, arguments=None, pid=None, timeout=30):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        return failure("invalid_timeout", "timeout must be in (0, 120] seconds")
    available = sessions()
    matches = [item for item in available if pid is None or item["pid"] == pid]
    if len(matches) != 1:
        return failure("session_selection", "Start the bridge in Blender, or specify a pid when multiple sessions exist.", available_pids=[item["pid"] for item in available])
    session = matches[0]
    data = json.dumps({"protocol": 1, "token": session["token"], "operation": operation, "arguments": arguments or {}, "timeout": timeout, "expires_at": time.time() + timeout}, ensure_ascii=True).encode() + b"\n"
    if len(data) > MAX_MESSAGE:
        return failure("request_too_large", "Request exceeds 1 MiB; no request sent")
    sent = False
    try:
        with socket.create_connection(("127.0.0.1", session["port"]), timeout=3) as connection:
            connection.settimeout(timeout + 5)
            sent = True  # Partial send is also ambiguous.
            connection.sendall(data)
            with connection.makefile("rb") as stream:
                line = stream.readline(MAX_MESSAGE + 1)
            if len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
                return failure("invalid_response", "Truncated or oversized reply; execution may have completed. Do not retry automatically.")
            response = json.loads(line)
            if not isinstance(response, dict) or type(response.get("ok")) is not bool:
                raise ValueError("Invalid reply envelope")
            return response
    except (OSError, ValueError) as exc:
        return failure("connection_error", "Connection failed; execution may have completed. Do not retry automatically." if sent else "Cannot reach Blender bridge; restart it in Blender if this session is stale.", detail=str(exc), execution_uncertain=sent)
