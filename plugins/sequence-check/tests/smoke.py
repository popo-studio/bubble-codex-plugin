"""Run with the plugin development environment; uses the deployed launcher."""
import asyncio
import json
import os
from pathlib import Path
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which('uv') or str(Path.home() / 'AppData/Roaming/Python/Python310/Scripts/uv.exe')
    params = StdioServerParameters(command=uv, args=['run', '--python', '3.13', '--no-project', '--no-config', '--directory', '/', '--locked', '--script', str(root / 'launch-0.2.0.py')], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            names = {t.name for t in (await client.list_tools()).tools}
            assert names == {'sequence_status', 'sequence_discover', 'sequence_inspect', 'sequence_write_report'}, names
            result = await client.call_tool('sequence_status', {})
            payload = result.structuredContent or json.loads(result.content[0].text)
            assert not result.isError and payload['ok'], result
            assert payload['data']['version'] == '0.2.0', payload
            assert payload['data']['pillow'] == '13.0.0', payload
            assert payload['data']['openexr'] == '3.4.9', payload
            print(payload)

asyncio.run(main())
