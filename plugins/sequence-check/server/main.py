"""Read-only MCP sequence tools."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import qc

mcp = FastMCP('Bubble Sequence Check')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

def result(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:500]}

@mcp.tool(annotations=READ)
def sequence_status() -> dict:
    """Harmless decoder availability/version and inspection limits. No scan or writes."""
    import PIL
    return {'ok': True, 'data': {'version': '0.1.1', 'pillow': PIL.__version__, 'openexr': qc.OpenEXR.__version__, 'max_files': qc.MAX_FILES, 'max_pixels': qc.MAX_PIXELS, 'max_decode_bytes': qc.MAX_DECODE_BYTES}}

@mcp.tool(annotations=READ)
def sequence_discover(directory: str, pattern: str = '*') -> dict:
    """Group numbered image filenames in one explicit absolute directory. Nonrecursive filename glob; max 1000 files/10000 directory entries. Last digit run before extension is frame number, padding variants share a group. No files is not a pass."""
    return result(qc.discover, directory, pattern)

@mcp.tool(annotations=READ)
def sequence_inspect(directory: str, pattern: str = '*', expected_start: int | None = None, expected_end: int | None = None) -> dict:
    """Read-only full image decode QC: gaps/duplicate frame numbers, corrupt files, layout changes, nonfinite pixels, suspected black and identical decoded pixels. Provide both expected endpoints to catch missing ends. PNG/JPEG/TIFF/BMP and flat multipart EXR supported; deep/multilevel EXR coverage limited. Limits return unverified/errors, never a clean verdict. No output files or source changes."""
    return result(qc.inspect, directory, pattern, expected_start, expected_end)

if __name__ == '__main__':
    mcp.run(transport='stdio')
