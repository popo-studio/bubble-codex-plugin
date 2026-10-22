"""Exercise new workflow actions through deployed MCP launchers on scratch data.

No production scene, farm job or software-side configuration is changed.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

import OpenEXR
import numpy as np
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def png(path):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0" * 2) * 2)) + chunk(b"IEND", b""))


def exr_fixtures(folder):
    """Write real flat float EXRs with the patched, locked fixture encoder."""
    assert OpenEXR.__version__ == "3.4.9", "Run with the sequence-check locked Python 3.13 environment"
    channels = {name: np.full((3, 4), value, dtype=np.float32)
                for name, value in (("R", .25), ("G", .5), ("B", .75))}
    OpenEXR.File({}, dict(channels)).write(str(folder / "linear.0001.exr"))
    channels["R"][0, 0] = np.nan
    channels["B"][2, 3] = np.inf
    OpenEXR.File({}, dict(channels)).write(str(folder / "linear.0002.exr"))
    # A truncated *real* image must produce a per-frame error, not a clean verdict.
    original = (folder / "linear.0001.exr").read_bytes()
    (folder / "linear.0003.exr").write_bytes(original[:20])


async def call(client, name, arguments, ok=True):
    response = await client.call_tool(name, arguments)
    assert not response.isError, (name, response)
    payload = response.structuredContent
    if not isinstance(payload, dict):
        payload = json.loads(next(c.text for c in response.content if c.type == "text"))
    assert payload.get("ok") is ok, (name, payload)
    return payload


async def check(name, workspace, action):
    package = ROOT / "plugins" / name
    config = next(iter(json.loads((package / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"].values()))
    params = StdioServerParameters(command=os.environ.get("UV_BIN") or shutil.which("uv"),
        args=[a.replace("${PLUGIN_ROOT}", str(package)) for a in config["args"]], cwd=str(package))
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as client:
            await client.initialize()
            await action(client, workspace)
    print("PASS functional MCP workflow:", name, flush=True)


async def sequence(client, workspace):
    folder = workspace / "source"
    status = await call(client, "sequence_status", {})
    assert status["data"]["pillow"] == "13.0.0", status
    assert status["data"]["openexr"] == "3.4.9", status
    result = await call(client, "sequence_discover", {"directory": str(folder), "pattern": "beauty.*.png"})
    assert result["data"][0]["files"] == 2, result
    result = await call(client, "sequence_inspect", {"directory": str(folder), "pattern": "beauty.*.png", "expected_start": 1, "expected_end": 3})
    row = result["data"][0]
    assert row["missing_frames"] == [2], row
    assert all(f["status"] == "decoded" for f in row["frames"]), row
    assert row["frames"][1]["same_pixels_as"] == "beauty.0001.png", row
    before = {path.name: path.read_bytes() for path in folder.glob("*.exr")}
    result = await call(client, "sequence_inspect", {
        "directory": str(folder), "pattern": "linear.*.exr",
        "expected_start": 1, "expected_end": 3})
    assert len(result["data"]) == 1, result
    row = result["data"][0]
    assert row["missing_frames"] == [], row
    frames = {frame["file"]: frame for frame in row["frames"]}
    assert len(frames) == 3, row
    for name in ("linear.0001.exr", "linear.0002.exr"):
        frame = frames[name]
        assert frame["status"] == "decoded", frame
        assert len(frame["parts"]) == 1, frame
        part = frame["parts"][0]
        assert (part["width"], part["height"]) == (4, 3), frame
        assert part["channels"] == ["B", "G", "R"], frame
        assert frame["layout_mismatch"] is False, frame
    assert frames["linear.0001.exr"]["nonfinite_samples"] == 0, frames
    assert frames["linear.0002.exr"]["nonfinite_samples"] == 2, frames
    assert frames["linear.0003.exr"]["status"] == "error", frames
    assert frames["linear.0003.exr"]["reason"], frames
    assert before == {path.name: path.read_bytes() for path in folder.glob("*.exr")}, "EXR inspection modified source files"


async def package(client, workspace):
    source, destination = workspace / "source", workspace / "delivery"
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    preview = await call(client, "package_preview", {"paths": [str(source / "beauty.####.png")], "destination": str(destination), "project_root": str(source)})
    assert preview["ready"] and len(preview["plan"]["files"]) == 2, preview
    args = {"plan": preview["plan"], "plan_hash": preview["plan_hash"]}
    await call(client, "package_execute", args, ok=False)
    assert not destination.exists(), "Unconfirmed execution wrote a directory"
    result = await call(client, "package_execute", {**args, "confirmed": True})
    assert result["verification"]["ok"], result
    await call(client, "package_verify", {"destination": str(destination)})
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}, "Sources changed"
    target = destination / "project/beauty.0001.png"
    target.write_bytes(b"deliberate damage to scratch delivery copy")
    result = await call(client, "package_verify", {"destination": str(destination)}, ok=False)
    assert result["problems"], result
    await call(client, "package_preview", {"paths": [str(source / "beauty.0001.png")], "destination": str(destination)}, ok=False)


async def doctor(client, workspace):
    result = await call(client, "doctor_check_package", {"package_path": str(ROOT / "plugins/plugin-doctor")})
    assert result["data"]["name"] == "plugin-doctor", result
    result = await call(client, "doctor_list_sessions", {"app": "maya", "session_directory": str(workspace / "no-sessions")})
    assert result["data"] == [], result
    log = workspace / "startup.log"
    log.write_text("secret=SHOULD_NOT_APPEAR\nWarning: name '__file__' is not defined\n", encoding="utf-8")
    result = await call(client, "doctor_check_log", {"log_path": str(log)})
    assert result["data"]["findings"][0]["code"] == "maya_loader_file_context", result
    assert "SHOULD_NOT_APPEAR" not in json.dumps(result)
    result = await call(client, "doctor_repair_guidance", {"plugin_name": "maya-control", "action": "uninstall"})
    assert result["data"]["executed"] is False


async def main():
    parent = ROOT / ".test-runtime"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workflow-", dir=parent) as directory:
        workspace = Path(directory)
        (workspace / "source").mkdir()
        png(workspace / "source/beauty.0001.png")
        png(workspace / "source/beauty.0003.png")
        exr_fixtures(workspace / "source")
        for name, action in (("sequence-check", sequence), ("asset-package", package), ("plugin-doctor", doctor)):
            await asyncio.wait_for(check(name, workspace, action), timeout=180)


if __name__ == "__main__":
    asyncio.run(main())
