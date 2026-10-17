"""Exercise real manifests without DCC apps or real profile changes.

Run with a Python that has the locked MCP dependency installed. UV_BIN can
select uv; UV_CACHE_DIR can select an external cache for offline reruns.
Unlike a static manifest test, this deletes each package while TWO connected
MCP processes are alive, then requests their tool lists again. On Windows this
catches executable, DLL, and working-directory handles inside the package.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def check_plugin(source, workspace, uv):
    package = workspace / source.name
    shutil.copytree(source, package, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "*.pyc",
        ".test-runtime", ".cache", ".git", "dist"))
    package = package.resolve()
    # Observe the real child interpreter at Python startup. This test-only
    # hook lives outside the plugin and does not modify its launcher or args.
    probe = workspace / (source.name + "-probe")
    probe.mkdir()
    (probe / "sitecustomize.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['BUBBLE_LAUNCH_PROBE'], str(os.getpid()) + '.json').write_text("
        "json.dumps({'prefix':sys.prefix,'executable':sys.executable,'cwd':os.getcwd(),'argv':sys.argv}))\n",
        encoding="utf-8")
    config = next(iter(json.loads((package / "mcp.json").read_text(encoding="utf-8"))["mcpServers"].values()))
    params = StdioServerParameters(
        command=uv,
        args=[arg.replace("${PLUGIN_ROOT}", str(package)) for arg in config["args"]],
        cwd=config["cwd"],
        env={**os.environ, "PYTHONPATH": str(probe), "BUBBLE_LAUNCH_PROBE": str(probe)},
    )
    async with stdio_client(params) as first_streams:
        async with ClientSession(*first_streams) as first:
            await first.initialize()
            first_tools = await first.list_tools()
            assert first_tools.tools, source.name
            # Simulate the next version's launcher at the SAME installed path.
            # uv caches PEP 723 environments by script path; --isolated is a
            # no-op for those scripts. Release filenames must change instead.
            old_launcher = Path(params.args[-1])
            next_launcher = old_launcher.with_name("launch-next-release.py")
            shutil.copyfile(old_launcher, next_launcher)
            shutil.copyfile(str(old_launcher) + ".lock", str(next_launcher) + ".lock")
            updated_config = json.loads((package / "mcp.json").read_text(encoding="utf-8"))
            next(iter(updated_config["mcpServers"].values()))["args"][-1] = "${PLUGIN_ROOT}/" + next_launcher.name
            (package / "mcp.json").write_text(json.dumps(updated_config), encoding="utf-8")
            updated = StdioServerParameters(command=params.command, args=[*params.args[:-1], str(next_launcher)], cwd=params.cwd, env=params.env)
            async with stdio_client(updated) as second_streams:
                async with ClientSession(*second_streams) as second:
                    await second.initialize()
                    second_tools = await second.list_tools()
                    records = [json.loads(p.read_text()) for p in probe.glob("*.json")]
                    launch_paths = {str(p).replace("\\", "/") for p in (old_launcher, next_launcher)}
                    servers = [r for r in records if any(arg.replace("\\", "/") in launch_paths for arg in r["argv"])]
                    assert len(servers) == 2, records
                    assert len({r["prefix"] for r in servers}) == 2, servers
                    for record in servers:
                        for field in ("prefix", "executable", "cwd"):
                            assert not Path(record[field]).resolve().is_relative_to(package), record
                    assert not (package / ".venv").exists()
                    assert not list((package / "server").rglob("__pycache__"))
                    # The target is freshly copied, resolved, and verified to
                    # remain inside this test's dedicated temporary directory.
                    assert package.parent == workspace.resolve()
                    shutil.rmtree(package)
                    assert not package.exists()
                    assert (await first.list_tools()).tools == first_tools.tools
                    assert (await second.list_tools()).tools == second_tools.tools
    print(f"PASS {source.name}: separate release runtimes; deleted live package; both still respond")


async def main():
    uv = os.environ.get("UV_BIN") or shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required; set UV_BIN to its executable")
    temp_parent = ROOT / ".test-runtime"
    temp_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="launcher-", dir=temp_parent) as directory:
        for source in sorted((ROOT / "plugins").glob("*-control")):
            await asyncio.wait_for(check_plugin(source, Path(directory), uv), timeout=180)


if __name__ == "__main__":
    asyncio.run(main())
