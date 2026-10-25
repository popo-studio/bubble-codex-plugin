"""Register a user-selected native MCP export; never modify Maxon/client files."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

OWNER = "bubble-cinema4d-native-config-v1"


def registry_path():
    return Path(os.environ.get("BUBBLE_CINEMA4D_CONFIG_DIR", str(Path.home() / ".bubble" / "cinema4d"))) / "connections.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Configuration exceeds 1 MiB")
    return raw, json.loads(raw.decode("utf-8-sig"))


def read_registry():
    path = registry_path()
    if path.is_symlink():
        raise ValueError("Registry must not be a symbolic link")
    if not path.exists():
        return {"owner": OWNER, "connections": {}}, digest(b"")
    raw, data = read_json(path)
    if not isinstance(data, dict) or data.get("owner") != OWNER or not isinstance(data.get("connections"), dict):
        raise ValueError("Unrecognized registry; refusing changes")
    return data, digest(raw)


def native_entry(path, entry_name):
    source = Path(path)
    if not source.is_absolute() or not source.is_file():
        raise ValueError("Choose an existing absolute path to your Maxon-exported MCP JSON")
    raw, data = read_json(source)
    entries = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(entries, dict) or entry_name not in entries:
        raise ValueError("Choose an exact entry in the exported mcpServers object")
    cfg = entries[entry_name]
    if not isinstance(cfg, dict) or cfg.get("disabled"):
        raise ValueError("Entry is invalid or disabled")
    if "command" in cfg:
        allowed = {"command", "args", "env", "cwd", "type", "transport", "disabled"}
        if set(cfg) - allowed or cfg.get("type", "stdio") != "stdio" or cfg.get("transport", "stdio") != "stdio":
            raise ValueError("Unsupported stdio configuration fields; do not guess their meaning")
        if not isinstance(cfg["command"], str) or not cfg["command"].strip():
            raise ValueError("Missing native command")
        if not isinstance(cfg.get("args", []), list) or not all(isinstance(x, str) for x in cfg.get("args", [])):
            raise ValueError("Invalid native arguments")
        if not isinstance(cfg.get("env", {}), dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in cfg.get("env", {}).items()):
            raise ValueError("Invalid native environment")
        if cfg.get("cwd") is not None and (not isinstance(cfg["cwd"], str) or not Path(cfg["cwd"]).is_absolute() or not Path(cfg["cwd"]).is_dir()):
            raise ValueError("Native cwd must be an existing absolute directory")
        kind = "stdio"
    else:
        allowed = {"url", "headers", "type", "transport", "disabled"}
        kind = cfg.get("type", cfg.get("transport", "streamable-http"))
        if kind == "http":
            kind = "streamable-http"
        if set(cfg) - allowed or kind not in ("streamable-http", "sse"):
            raise ValueError("Unsupported HTTP configuration fields or transport")
        url = urlsplit(cfg.get("url", ""))
        if url.scheme not in ("http", "https") or url.hostname not in ("127.0.0.1", "::1", "localhost") or url.username or url.password or url.fragment:
            raise ValueError("Only explicit local loopback HTTP endpoints are supported")
        headers = cfg.get("headers", {})
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise ValueError("Invalid native HTTP headers")
    return cfg, kind, digest(raw)


def status():
    data, revision = read_registry()
    return {"registry_path": str(registry_path()), "revision": revision, "connections": [{"name": name, "config_path": v["config_path"], "entry_name": v["entry_name"], "transport": v["transport"]} for name, v in data["connections"].items()], "host_installation": "Uses Cinema 4D 2027 built-in MCP; no Bubble host plugin to install", "native_acceptance": "Not tested in Cinema 4D on this development machine"}


def change(action, name, config_path="", entry_name="", confirmed=False, expected_revision="", expected_config_hash=""):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("Connection name must be 1-64 letters, digits, underscores or hyphens")
    data, revision = read_registry()
    proposed = None
    if action == "register":
        _, kind, config_hash = native_entry(config_path, entry_name)
        proposed = {"config_path": str(Path(config_path).resolve()), "entry_name": entry_name, "transport": kind, "config_hash": config_hash}
    elif action != "remove":
        raise ValueError("Action must be register or remove")
    preview = {"action": action, "name": name, "registry_path": str(registry_path()), "revision": revision, "config_hash": proposed["config_hash"] if proposed else "", "changes": proposed, "confirmed": False, "note": "Only a path and fingerprint are stored. Exported config may contain credentials; keep it private. Stdio config starts the exact authorized program when connect is called. Native preferences are never modified."}
    if not confirmed:
        return preview
    if expected_revision != revision or (proposed and expected_config_hash != proposed["config_hash"]):
        raise ValueError("Preview is stale or missing; preview and authorize the exact configuration again")
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    tmp = None
    try:
        os.close(fd)
        _, current = read_registry()
        if current != revision:
            raise ValueError("Registry changed concurrently; preview again")
        if proposed:
            data["connections"][name] = proposed
        else:
            data["connections"].pop(name, None)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix="connections-", suffix=".tmp", delete=False) as stream:
            tmp = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        preview["confirmed"] = True
        return preview
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
        lock.unlink()


def load_connection(name):
    data, _ = read_registry()
    record = data["connections"].get(name)
    if not record:
        raise ValueError("Connection is not registered")
    cfg, kind, fingerprint = native_entry(record["config_path"], record["entry_name"])
    if fingerprint != record["config_hash"] or kind != record["transport"]:
        raise ValueError("Native config changed; preview and authorize registration again")
    return cfg, kind, fingerprint
