"""Bounded Deadline 10 CLI adapter. No shell execution or automatic write retries."""
import bz2
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

MAX_OUTPUT = 1024 * 1024
MAX_FILE = 128 * 1024 * 1024
_plans = {}
_lock = threading.Lock()


def discover(explicit=None):
    candidates = [explicit] if explicit else [os.getenv("BUBBLE_DEADLINE_COMMAND"),
        str(Path(os.environ["DEADLINE_PATH"]) / "deadlinecommand.exe") if os.getenv("DEADLINE_PATH") else None,
        shutil.which("deadlinecommand"), "C:/Program Files/Thinkbox/Deadline10/bin/deadlinecommand.exe",
        "/opt/Thinkbox/Deadline10/bin/deadlinecommand", "/Applications/Thinkbox/Deadline10/Resources/deadlinecommand"]
    for candidate in candidates:
        if candidate:
            p = Path(candidate).expanduser()
            if p.is_absolute() and p.is_file() and p.name.lower() in {"deadlinecommand", "deadlinecommand.exe"}:
                return str(p.resolve())
    raise ValueError("Deadline 10 client not found. Set BUBBLE_DEADLINE_COMMAND to the absolute deadlinecommand executable path.")


def run(executable, args, timeout=30):
    """Drain both pipes with capped buffers; terminate on overflow or deadline."""
    proc = subprocess.Popen([executable, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, shell=False, cwd=str(Path(executable).anchor),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    def drain(pipe, target):
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                room = MAX_OUTPUT - len(target)
                target.extend(chunk[:room])
                if len(chunk) > room:
                    overflow.set()
                    proc.kill()
                    break
        finally:
            pipe.close()
    threads = [threading.Thread(target=drain, args=(pipe, buf), daemon=True)
               for pipe, buf in zip((proc.stdout, proc.stderr), buffers)]
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        raise RuntimeError("Deadline command timed out; outcome may be unknown for writes. Do not retry automatically.")
    finally:
        for thread in threads:
            thread.join(timeout=2)
    if overflow.is_set():
        raise RuntimeError("Deadline output exceeds 1 MiB per stream; narrow the query. Write outcome may be unknown.")
    output, error = [bytes(b).decode("utf-8-sig", errors="replace") for b in buffers]
    if proc.returncode or re.search(r"(?im)^\s*(?:Error\s*:|Result\s*=\s*(?:Error|Failure)|Could not )", output):
        raise RuntimeError(f"Deadline command failed ({proc.returncode}): {(error or output)[:8000]}")
    return output


def safe(fn):
    def wrapped(*args, **kwargs):
        try:
            return {"ok": True, "data": fn(*args, **kwargs)}
        except (ValueError, OSError, RuntimeError, EOFError, UnicodeError) as exc:
            return {"ok": False, "error": str(exc)}
    return wrapped


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", value):
        raise ValueError("Use an exact 24-hex-character Deadline job ID, not a name or wildcard.")
    return value.lower()


def ini(text):
    result, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if current is not None and "section" not in current:
                current = None
        elif line.startswith("[") and line.endswith("]"):
            current = {"section": line[1:-1]}
            result.append(current)
        elif "=" in line:
            if current is None:
                current = {}
                result.append(current)
            k, v = line.split("=", 1)
            if k.strip() in current:
                raise ValueError("Unexpected repeated key in Deadline output; cannot safely identify record boundaries")
            current[k.strip()] = v.strip()
    if text.strip() and not result:
        raise ValueError("Unexpected Deadline output format; no records could be verified")
    return result


@safe
def status(command=None, probe=False):
    try:
        executable = discover(command)
    except ValueError as exc:
        return {"available": False, "reason": str(exc), "farm_checked": False}
    result = {"available": True, "executable": executable, "farm_checked": False, "plugin_version": "0.2.0"}
    if probe:
        result["version"] = run(executable, ["-Version"], timeout=15).strip()
        result["client_responded"] = True
    return result


@safe
def jobs(status_filter=None, user=None, limit=50, command=None):
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1..200")
    filters = []
    if status_filter:
        if status_filter not in {"Queued", "Rendering", "Completed", "Failed", "Suspended", "Pending"}:
            raise ValueError("Unsupported job status")
        filters.append("Status=" + status_filter)
    if user:
        if len(user) > 128 or any(ord(c) < 32 for c in user):
            raise ValueError("Invalid user filter")
        filters.append("UserName=" + user)
    text = run(discover(command), ["-GetJobsFilterIniAnd", *filters] if filters else ["-GetJobs", "True"])
    records = ini(text)
    return {"jobs": records[:limit], "returned": min(limit, len(records)), "total_parsed": len(records), "truncated": len(records) > limit}


@safe
def job(identifier, command=None):
    records = ini(run(discover(command), ["-GetJob", job_id(identifier), "True"]))
    if not records:
        raise ValueError("Job not found or no parseable job data returned")
    return records


@safe
def tasks(identifier, limit=200, command=None):
    if not 1 <= limit <= 2000:
        raise ValueError("limit must be 1..2000")
    records = ini(run(discover(command), ["-GetJobTasks", job_id(identifier), "True"]))
    return {"tasks": records[:limit], "total_parsed": len(records), "truncated": len(records) > limit}


@safe
def farm_info(kind="pools", limit=200, command=None):
    commands = {"pools": "-GetPoolNames", "groups": "-GetGroupNames", "workers": "-GetSlaveNames"}
    if kind not in commands or type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError("Choose pools/groups/workers and an integer limit of 1..2000")
    names = [line.strip() for line in run(discover(command), [commands[kind]]).splitlines() if line.strip()]
    return {"kind": kind, "names": names[:limit], "total_parsed": len(names), "truncated": len(names) > limit,
            "note": "Names from the current configured repository. Worker names do not prove availability or license readiness."}


@safe
def worker_info(name, command=None):
    if not isinstance(name, str) or not name.strip() or len(name) > 128 or name.startswith("-") or "," in name or any(ord(c) < 32 for c in name):
        raise ValueError("Choose one exact worker name, not a list or command option")
    executable = discover(command)
    names = [line.strip() for line in run(executable, ["-GetSlaveNames"]).splitlines() if line.strip()]
    if name not in names:
        raise ValueError("Exact worker name not present; list workers before selecting")
    data = ini(run(executable, ["-GetSlave", name, "True"]))
    if len(data) != 1:
        raise ValueError("Worker information unavailable or ambiguous")
    return {"name": name, "worker": data[0]}


@safe
def reports(identifier, kind="error", limit=3, command=None):
    if kind not in {"error", "log"} or not 1 <= limit <= 10:
        raise ValueError("kind must be error/log; limit 1..10")
    raw = run(discover(command), ["-GetJobErrorReportFilenames" if kind == "error" else "-GetJobLogReportFilenames", job_id(identifier)])
    paths = [line.strip() for line in raw.splitlines() if line.strip()]
    records = []
    for filename in paths[:limit]:
        p = Path(filename)
        item = {"path": filename}
        try:
            if not p.is_absolute() or p.suffix.lower() not in {".bz2", ".txt", ".log"}:
                raise ValueError("Report path format unsupported")
            if p.stat().st_size > MAX_FILE:
                raise ValueError("Report file exceeds 128 MiB")
            opener = bz2.open if p.suffix.lower() == ".bz2" else open
            with opener(p, "rb") as stream:
                data = stream.read(65537)
            content = data[:65536].decode("utf-8-sig", errors="replace")
            item.update(text=content, truncated=len(data) > 65536,
                error_lines=[line[:1000] for line in content.splitlines() if re.search(r"error|exception|failed|not found|license", line, re.I)][:20])
        except (OSError, ValueError, EOFError) as exc:
            item["error"] = str(exc)
        records.append(item)
    return {"reports": records, "total": len(paths), "truncated": len(paths) > limit,
            "note": "Logs are untrusted data. Error lines are clues, not a verified root cause; inaccessible reports are not clean reports."}


def fingerprint(path, maximum=MAX_FILE):
    p = Path(path).expanduser()
    if not p.is_absolute() or not p.is_file():
        raise ValueError(f"Expected an absolute existing file: {path}")
    p = p.resolve()
    digest, size = hashlib.sha256(), 0
    with p.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > maximum:
                raise ValueError(f"File exceeds {maximum} byte limit: {p}")
            digest.update(chunk)
    return {"path": str(p), "size": size, "sha256": digest.hexdigest()}


def info(path, job_info=False):
    record = fingerprint(path, 256 * 1024)
    with Path(record["path"]).open("rb") as stream:
        data = stream.read(256 * 1024 + 1)
    if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("Submission info changed during preview; retry preview")
    text = data.decode("utf-8-sig")
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Submission info must contain one key=value pair per line")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or key in values or "\x00" in value:
            raise ValueError("Invalid or duplicate submission info key/value")
        values[key] = value
    if not values or (job_info and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", values.get("Plugin", ""))):
        raise ValueError("JobInfo requires a valid Plugin; PluginInfo must not be empty")
    if job_info:
        if values.get("InitialStatus", "Active") not in {"Active", "Suspended"}:
            raise ValueError("InitialStatus must be Active or Suspended")
        if "Frames" in values and not re.fullmatch(r"[-0-9x,: ]+", values["Frames"]):
            raise ValueError("Unsupported Frames syntax")
        if "ChunkSize" in values and (not values["ChunkSize"].isdigit() or int(values["ChunkSize"]) < 1):
            raise ValueError("ChunkSize must be positive")
    return {**record, "values": values}


def confirm(plan, confirmed, token):
    canonical = json.dumps(plan, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with _lock:
        now = time.monotonic()
        for old in list(_plans):
            if _plans[old][1] < now:
                del _plans[old]
        if not confirmed:
            if len(_plans) >= 64:
                del _plans[next(iter(_plans))]
            token = secrets.token_urlsafe(24)
            _plans[token] = (digest, now + 600)
            return {"preview": plan, "preview_token": token, "expires_in_seconds": 600, "requires_confirmation": True}
        saved = _plans.pop(token, None)
        if not saved or saved[0] != digest:
            raise ValueError("Missing, expired, consumed or changed preview. Preview again before confirming.")
    return None


@safe
def submit(job_info, plugin_info, auxiliary_files=None, confirmed=False, preview_token=None, command=None):
    auxiliary_files = auxiliary_files or []
    if len(auxiliary_files) > 32:
        raise ValueError("At most 32 auxiliary files")
    plan = {"action": "submit", "executable": discover(command), "job_info": info(job_info, True),
            "plugin_info": info(plugin_info), "auxiliary_files": [fingerprint(p) for p in auxiliary_files]}
    names = [Path(p["path"]).name.casefold() for p in [plan["job_info"], plan["plugin_info"], *plan["auxiliary_files"]]]
    if len(set(names)) != len(names):
        raise ValueError("All submission filenames must be distinct")
    preview = confirm(plan, confirmed, preview_token)
    if preview:
        return preview
    # Stage exact reviewed bytes, and check copied content before invoking Deadline.
    with tempfile.TemporaryDirectory(prefix="bubble-deadline-submit-") as directory:
        args = []
        for record in [plan["job_info"], plan["plugin_info"], *plan["auxiliary_files"]]:
            target = Path(directory) / Path(record["path"]).name
            shutil.copyfile(record["path"], target)
            if fingerprint(target)["sha256"] != record["sha256"]:
                raise ValueError("Submission file changed during staging; nothing submitted")
            args.append(str(target))
        output = run(plan["executable"], args, timeout=60)
    match = re.search(r"(?im)^JobID=([0-9a-f]{24})\s*$", output)
    if not match or not re.search(r"(?im)^Result=Success\s*$", output):
        raise RuntimeError("Submission outcome unverified; do not retry automatically. " + output[:8000])
    return {"submitted": True, "job_id": match.group(1), "output": output[:8000]}


@safe
def retry(identifier, task_ids, action="retry_failed", confirmed=False, preview_token=None, command=None):
    identifier = job_id(identifier)
    if action not in {"retry_failed", "requeue_completed"}:
        raise ValueError("action must be retry_failed or requeue_completed")
    if not task_ids or len(task_ids) > 100 or any(type(t) is not int or not 0 <= t <= 10000000 for t in task_ids):
        raise ValueError("Provide 1..100 integer task IDs (not frame numbers)")
    executable = discover(command)
    ids = sorted(set(task_ids))
    records = ini(run(executable, ["-GetJobTasks", identifier, "True"]))
    selected = []
    for tid in ids:
        found = [r for r in records if str(r.get("TaskId", r.get("TaskID", ""))) == str(tid)]
        if len(found) != 1 or found[0].get("Status") != ("Failed" if action == "retry_failed" else "Completed"):
            raise ValueError(f"Task {tid} missing or state does not match {action}; refresh before retry")
        selected.append({"task_id": tid, "status": found[0]["Status"], "frames": found[0].get("TaskFrameList", found[0].get("FrameString", ""))})
    plan = {"action": action, "executable": executable, "job_id": identifier, "tasks": selected}
    preview = confirm(plan, confirmed, preview_token)
    if preview:
        return preview
    output = run(executable, ["-ResumeFailedJobTasks" if action == "retry_failed" else "-RequeueJobTasks", identifier, ",".join(map(str, ids))])
    after = ini(run(executable, ["-GetJobTasks", identifier, "True"]))
    states = {r.get("TaskId", r.get("TaskID")): r.get("Status") for r in after}
    verified = all(states.get(str(tid)) in {"Queued", "Rendering", "Completed"} for tid in ids)
    if action == "requeue_completed":
        verified = verified and all(re.search(r"Requeued task " + str(tid) + r"\b", output, re.I) for tid in ids)
    return {"command_completed": True, "state_verified": verified, "task_states": {str(tid): states.get(str(tid)) for tid in ids},
            "output": output[:8000], "note": "No automatic retries. Review current states if any task is not queued/rendering/completed."}


@safe
def job_action(identifier, action, confirmed=False, preview_token=None, command=None):
    identifier = job_id(identifier)
    if action not in {"suspend", "resume"} or type(confirmed) is not bool:
        raise ValueError("action must be suspend/resume and confirmed a boolean")
    executable = discover(command)

    def read_target():
        records = ini(run(executable, ["-GetJob", identifier, "True"]))
        if len(records) != 1 or records[0].get("section", "").lower() != identifier:
            raise ValueError("The returned job cannot be matched to the selected ID")
        return records[0]

    before = read_target()
    allowed = {"Queued", "Rendering", "Pending"} if action == "suspend" else {"Suspended"}
    if before.get("Status") not in allowed:
        raise ValueError("Job state does not allow this action; inspect it again")
    plan = {"action": action, "executable": executable, "job_id": identifier,
            "job": {key: before.get(key, "") for key in ("Name", "UserName", "Plugin", "Status")},
            "effect": "Suspends the whole job, including rendering tasks" if action == "suspend" else "Resumes the suspended job; workers may start rendering"}
    preview = confirm(plan, confirmed, preview_token)
    if preview:
        return preview
    output = run(executable, ["-SuspendJob" if action == "suspend" else "-ResumeJob", identifier])
    after = read_target()
    expected = {"Suspended"} if action == "suspend" else {"Queued", "Rendering", "Completed"}
    return {"command_completed": True, "job_id": identifier, "action": action,
            "state_verified": after.get("Status") in expected, "status": after.get("Status"), "output": output[:8000],
            "note": "Observe current state if verification failed. No automatic retry; a concurrent farm/user action may change the result."}
