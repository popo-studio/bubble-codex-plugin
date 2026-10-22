"""Real locked deployment-launcher stdio protocol smoke, no user files."""
import asyncio
import json
from pathlib import Path
import sys
import os
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    uv = shutil.which('uv') or str(Path.home() / 'AppData/Roaming/Python/Python310/Scripts/uv.exe')
    launcher = Path(__file__).resolve().parents[1] / 'launch-0.1.1.py'
    params = StdioServerParameters(command=uv, args=['run', '--no-project', '--no-config', '--directory', '/', '--locked', '--script', str(launcher)], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {x.name for x in (await session.list_tools()).tools}
            assert names == {'package_status', 'package_preview', 'package_execute', 'package_verify'}, names
            result = await session.call_tool('package_status', {})
            data = result.structuredContent or json.loads(result.content[0].text)
            assert not result.isError and data['ok'], result
            print('4 tools discovered; package_status ok')


if __name__ == '__main__':
    asyncio.run(main())
