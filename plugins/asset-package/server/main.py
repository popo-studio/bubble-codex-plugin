"""MCP interface for explicit dependency delivery."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from package import prepare, execute, verify, MAX_FILES, MAX_BYTES

mcp = FastMCP('Bubble Asset Package')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def result(fn, *args):
    try:
        return fn(*args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'ok': False, 'error': str(exc)}


@mcp.tool(annotations=READ)
def package_status() -> dict:
    """Harmless plugin status; no files scanned and no DCC connection needed."""
    return {'ok': True, 'version': '0.1.1', 'max_files': MAX_FILES, 'max_bytes': MAX_BYTES, 'source_changes': False}


@mcp.tool(annotations=READ)
def package_preview(paths: list[str], destination: str, project_root: str | None = None, dependency_manifest: str | None = None) -> dict:
    """Hash explicit absolute files or filename tokens (<UDIM>, ####, %04d, $F4). Optional JSON manifest {paths: [absolute strings]}. Preview NEW destination outside source directories, mapping and missing inputs; no writes. Project files preserve layout under project/, others map under external/<parent-hash>/. Does NOT parse scene files or prove sequence completeness. Large inputs may take time; max 10000 files/100 GiB. Show plan and obtain user authorization before execution."""
    return result(prepare, paths, destination, project_root, dependency_manifest)


@mcp.tool(annotations=WRITE)
def package_execute(plan: dict, plan_hash: str, confirmed: bool = False) -> dict:
    """Copy the exact approved preview into a NEW folder only. Set confirmed only after user authorizes displayed destination/mapping. Rehashes sources and rejects changed plans or missing dependencies. No source changes/overwrites; failure retains partial output and requires a new destination to retry. Does not rewrite scene paths. Not safe against hostile concurrent filesystem mutation; use stable source and destination directories."""
    return result(execute, plan, plan_hash, confirmed)


@mcp.tool(annotations=READ)
def package_verify(destination: str) -> dict:
    """Verify package-manifest.json entries by size and SHA256. Read-only; reports missing/mismatching files. Extra files and scene portability are not verified; unsigned manifest is not proof against malicious replacement."""
    return result(verify, destination)


if __name__ == '__main__':
    mcp.run(transport='stdio')
