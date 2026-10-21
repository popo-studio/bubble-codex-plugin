"""Per-MCP-process, authenticated loopback CEP broker. No retry or session guessing."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
import threading
import time
import uuid
import ntpath

MAX_MESSAGE = 1024 * 1024


def failure(code, message, **details):
    return {"ok": False, "error": {"code": code, "message": message, **details}}


class Broker:
    def __init__(self, application="premiere"):
        self.application = application
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.clients = {}
        self.jobs = {}
        self.closed = False
        broker = self
        slots = threading.BoundedSemaphore(32)

        class Server(ThreadingHTTPServer):
            def process_request(self, request, address):
                if not slots.acquire(blocking=False):
                    request.close()
                    return
                try:
                    super().process_request(request, address)
                except Exception:
                    slots.release()
                    raise

            def process_request_thread(self, request, address):
                try:
                    super().process_request_thread(request, address)
                finally:
                    slots.release()

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *args):
                pass  # Never log pairing credentials, scripts, or document paths.

            def do_OPTIONS(self):
                # CEP file:// panels have an opaque/null origin. Tokens remain mandatory for POST.
                if self.headers.get("Origin") != "null":
                    return self.reply(403, failure("origin", "Only the local CEP panel origin is accepted"))
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "null")
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                self.connection.settimeout(3)
                supplied = self.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + broker.token).encode()):
                    return self.reply(401, failure("unauthorized", "Pair this panel first"))
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= MAX_MESSAGE:
                        return self.reply(413, failure("size", "Body must be at most 1 MiB"))
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("Expected an object")
                    self.reply(200, broker.handle(self.path, data))
                except (ValueError, OSError):
                    self.reply(400, failure("request", "Invalid JSON request"))

            def reply(self, status, value):
                raw = json.dumps(value, ensure_ascii=True).encode()
                if len(raw) > MAX_MESSAGE:
                    status, raw = 413, b'{"ok":false,"error":{"code":"size","message":"Response too large"}}'
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "no-store")
                    if self.headers.get("Origin") == "null":
                        self.send_header("Access-Control-Allow-Origin", "null")
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass

        self.http = Server(("127.0.0.1", 0), Handler)
        self.http.daemon_threads = True
        self.http.block_on_close = False
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def pairing(self):
        return {"ok": True, "data": {
            "connection_code": "bubble-premiere:1:%s:%s" % (self.http.server_port, self.token),
            "note": "Paste this private code into the Bubble panel and click Connect. "
                    "It grants this Codex process control. Keep the panel open. "
                    "Reconnect with a new code after Codex restarts; each chat has a separate broker."}}

    def _expire(self):
        now = time.time()
        for sid in list(self.clients):
            active = any(j["session_id"] == sid and j["delivered"] and
                         now < j["expires_at"] + 5 for j in self.jobs.values())
            if now - self.clients[sid]["seen"] > 15 and not active:
                del self.clients[sid]
        for job in self.jobs.values():
            if now >= job["expires_at"] and not job["event"].is_set():
                job["response"] = failure("timeout", "Deadline elapsed; never retry automatically.",
                                          execution_uncertain=job["delivered"])
                job["event"].set()

    def handle(self, path, data):
        with self.lock:
            self._expire()
            if self.closed:
                return failure("closed", "Broker stopped")
            if path == "/register":
                info = data.get("info")
                if not isinstance(info, dict) or info.get("app") != self.application:
                    return failure("application", "Pairing code belongs to a different Adobe application")
                if len(self.clients) >= 32:
                    return failure("limit", "Too many panels")
                sid = str(uuid.uuid4())
                self.clients[sid] = {"seen": time.time(), "info": self._info(data.get("info"))}
                return {"ok": True, "data": {"session_id": sid}}
            sid = data.get("session_id")
            if not isinstance(sid, str) or sid not in self.clients:
                return failure("session", "Session expired; reconnect explicitly")
            if path == "/unregister":
                del self.clients[sid]
                for job in self.jobs.values():
                    if job["session_id"] == sid and not job["event"].is_set():
                        job["response"] = failure("disconnected", "Panel disconnected; do not retry automatically.",
                                                  execution_uncertain=job["delivered"])
                        job["event"].set()
                return {"ok": True}
            self.clients[sid]["seen"] = time.time()
            if path == "/poll":
                self.clients[sid]["info"] = self._info(data.get("info"))
                for job in self.jobs.values():
                    if job["session_id"] == sid and not job["delivered"] and not job["event"].is_set():
                        job["delivered"] = True
                        return {"ok": True, "data": {k: job[k] for k in (
                            "request_id", "operation", "arguments", "expires_at")}}
                return {"ok": True, "data": None}
            if path == "/result":
                request_id = data.get("request_id")
                job = self.jobs.get(request_id) if isinstance(request_id, str) else None
                if not job or job["session_id"] != sid or not job["delivered"]:
                    return failure("request", "Unknown request")
                response = data.get("response")
                if not isinstance(response, dict) or type(response.get("ok")) is not bool:
                    return failure("response", "Invalid response envelope")
                if not job["event"].is_set():
                    job["response"] = response
                    job["event"].set()
                return {"ok": True}
            return failure("endpoint", "Unknown endpoint")

    @staticmethod
    def _info(info):
        if not isinstance(info, dict):
            return {"targets": [], "error": "Host information unavailable"}
        # Bounded, explicit public metadata only; no fabricated host PID.
        targets = info.get("targets", [])
        error = str(info.get("error", ""))[:1024]
        if not isinstance(targets, list) or len(targets) > 100:
            error = error or "Target list invalid or truncated; selection is incomplete"
        return {"version": str(info.get("version", ""))[:128],
                "targets": [{k: str(t.get(k, ""))[:4096] for k in ("id", "name", "path")}
                            for t in targets[:100] if isinstance(t, dict)] if isinstance(targets, list) else [],
                "error": error}

    def sessions(self, target=None):
        with self.lock:
            self._expire()
            rows = [{"session_id": sid, **v["info"]} for sid, v in self.clients.items()]
        query = target.strip() if isinstance(target, str) else None
        matches = []
        for row in rows:
            for item in row["targets"]:
                path, name = item["path"], item["name"]
                if query and ((("/" in query or "\\" in query) and
                               ntpath.normcase(ntpath.normpath(path)) == ntpath.normcase(ntpath.normpath(query)))
                              or (query.casefold() in (name.casefold(), ntpath.splitext(name)[0].casefold()))):
                    matches.append({"session_id": row["session_id"], "target_id": item["id"]})
        incomplete = any(row["error"] for row in rows)
        status = ("unspecified" if not query else "incomplete" if incomplete else
                  "unique" if len(matches) == 1 else "ambiguous" if matches else "not_found")
        return {"ok": True, "data": rows, "selection": {"status": status, "matches": matches,
                "selected": matches[0] if status == "unique" else None},
                "note": "Only paired open panels are visible. Session UUID identifies a panel, not a host PID. "
                        "Choose explicit session and target IDs; do not infer the first document/project."}

    def request(self, operation, arguments=None, session_id=None, timeout=30):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            return failure("timeout", "timeout must be in (0, 120]")
        with self.lock:
            self._expire()
            available = list(self.clients)
            if session_id is None:
                if len(available) != 1:
                    return failure("selection", "Choose one paired panel explicitly", sessions=available)
                session_id = available[0]
            if session_id not in self.clients:
                return failure("session", "Chosen panel is not connected; no fallback")
            if len(self.jobs) >= 32:
                return failure("busy", "Request queue full")
            job = {"request_id": str(uuid.uuid4()), "session_id": session_id,
                   "operation": operation, "arguments": arguments or {}, "expires_at": time.time() + timeout,
                   "delivered": False, "event": threading.Event()}
            if len(json.dumps({k: v for k, v in job.items() if k != "event"}).encode()) > MAX_MESSAGE - 1024:
                return failure("size", "Request exceeds limit")
            self.jobs[job["request_id"]] = job
        job["event"].wait(timeout)
        with self.lock:
            self.jobs.pop(job["request_id"], None)
            return job.get("response", failure("timeout", "Deadline elapsed; do not retry automatically.",
                                               execution_uncertain=job["delivered"]))

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job["response"] = failure("closed", "Broker stopped", execution_uncertain=job["delivered"])
                job["event"].set()
        self.http.shutdown()
        self.http.server_close()
