"""Read-only image inspection with explicitly requested report outputs."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import qc

mcp = FastMCP('Bubble Sequence Check')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

def result(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:500]}

@mcp.tool(annotations=READ)
def sequence_status() -> dict:
    """Harmless decoder availability/version and inspection limits. No scan or writes."""
    import PIL
    return {'ok': True, 'data': {'version': '0.2.0', 'pillow': PIL.__version__, 'openexr': qc.OpenEXR.__version__, 'max_files': qc.MAX_FILES, 'max_pixels': qc.MAX_PIXELS, 'max_decode_bytes': qc.MAX_DECODE_BYTES}}

@mcp.tool(annotations=READ)
def sequence_discover(directory: str, pattern: str = '*', signed_frames: bool = False) -> dict:
    """Group numbered image filenames in one explicit absolute directory. Nonrecursive filename glob; max 1000 files/10000 directory entries. Last digit run before extension is frame number, padding variants share a group. No files is not a pass."""
    return result(qc.discover, directory, pattern, signed_frames)

@mcp.tool(annotations=READ)
def sequence_inspect(directory: str, pattern: str = '*', expected_start: int | None = None, expected_end: int | None = None,
                     frame_step: int = 1, signed_frames: bool = False, expected_width: int | None = None,
                     expected_height: int | None = None, required_channels: list[str] | None = None) -> dict:
    """Read-only full image decode QC: gaps/duplicate frame numbers, corrupt files, layout changes, nonfinite pixels, suspected black and identical decoded pixels. Provide both expected endpoints to catch missing ends. PNG/JPEG/TIFF/BMP and flat multipart EXR supported; deep/multilevel EXR coverage limited. Limits return unverified/errors, never a clean verdict. No output files or source changes."""
    return result(qc.inspect, directory, pattern, expected_start, expected_end, frame_step, signed_frames, expected_width, expected_height, required_channels)

@mcp.tool(annotations=WRITE)
def sequence_write_report(directory: str, output_path: str, pattern: str = '*', expected_start: int | None = None,
                          expected_end: int | None = None, frame_step: int = 1, signed_frames: bool = False,
                          expected_width: int | None = None, expected_height: int | None = None,
                          required_channels: list[str] | None = None, confirmed: bool = False) -> dict:
    """Inspect a sequence and preview/write a NEW JSON or CSV report (max8MiB). Set confirmed only for a user-requested report at this exact path. Never overwrites or modifies images. CSV neutralizes formula-like text; JSON includes full details. Signed negative frames are opt-in because '-' may be a filename separator. Width/height apply to every decoded part; required channels to their union. Written report is not a QC pass; inspect findings."""
    return result(qc.write_report, directory, output_path, pattern, expected_start, expected_end, frame_step,
                  signed_frames, expected_width, expected_height, required_channels, confirmed)

if __name__ == '__main__':
    mcp.run(transport='stdio')
