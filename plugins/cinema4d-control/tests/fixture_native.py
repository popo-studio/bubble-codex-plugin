"""Synthetic native MCP endpoint. Not a substitute for Cinema 4D acceptance."""
import asyncio
import sys
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("Synthetic C4D transport fixture", host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv) > 2 else 8000)

@mcp.tool()
def fixture_echo(value: str) -> dict:
    return {"value": value, value: "key-test"}

@mcp.tool()
async def fixture_slow() -> str:
    await asyncio.sleep(10)
    return "done"

@mcp.tool()
def fixture_error() -> str:
    raise RuntimeError("SECRET-CREDENTIAL-DO-NOT-PRINT")

if __name__ == "__main__":
    mcp.run(transport=sys.argv[1] if len(sys.argv) > 1 else "stdio")
