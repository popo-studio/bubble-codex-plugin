"""Persistent, explicitly selected native MCP sessions. Never replay a call."""
import asyncio
from contextlib import AsyncExitStack
from datetime import timedelta
import os
import uuid
from urllib.parse import parse_qsl, urlsplit

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import NoSuchResource
from pydantic import AnyUrl
from configuration import load_connection


def local_http(headers=None, timeout=None, auth=None):
    # Credentials must not follow redirects or workstation proxy settings.
    return httpx.AsyncClient(headers=headers, timeout=timeout or 30, auth=auth, follow_redirects=False, trust_env=False)


def validate_arguments(schema, arguments):
    """Validate native JSON schema locally. Never retrieve external schema URLs."""
    def refuse(uri):
        raise NoSuchResource(ref=uri)
    try:
        validator = validator_for(schema)
        validator.check_schema(schema)
        validator(schema, registry=Registry(retrieve=refuse)).validate(arguments)
    except Exception:
        # Validation exceptions contain submitted values and credential-bearing refs.
        raise ValueError('Arguments do not match the discovered native schema, or its schema requires unsupported external references; no call submitted') from None


def redactor(cfg):
    secrets = [v for group in (cfg.get("headers", {}), cfg.get("env", {})) for v in group.values() if v]
    secrets += [v for v in cfg.get("args", []) if v and not v.startswith("-")]
    secrets += [v.split("=", 1)[1] for v in cfg.get("args", []) if "=" in v and v.split("=", 1)[1]]
    secrets += [v for _, v in parse_qsl(urlsplit(cfg.get("url", "")).query) if v]
    secrets += [v.split(" ", 1)[1] for v in list(secrets) if v.lower().startswith("bearer ")]
    secrets = sorted(set(secrets), key=len, reverse=True)
    def scrub(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[redacted]")
            return value
        if isinstance(value, dict):
            return {scrub(k): scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value
    return scrub


class NativeSession:
    def __init__(self, name, fingerprint):
        self.name = name
        self.fingerprint = fingerprint
        self.id = uuid.uuid4().hex
        self.queue = asyncio.Queue()
        self.ready = asyncio.get_running_loop().create_future()
        self.task = None
        self.alive = False
        self.tools = {}
        self.resources = {}
        self.has_resources = False

    async def run(self, cfg, kind):
        pending = None
        try:
            async with AsyncExitStack() as stack:
                if kind == "stdio":
                    # Native stderr can contain credentials. Do not forward it to Codex logs.
                    errlog = stack.enter_context(open(os.devnull, "w"))
                    params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"), cwd=cfg.get("cwd"))
                    streams = await stack.enter_async_context(stdio_client(params, errlog=errlog))
                elif kind == "sse":
                    streams = await stack.enter_async_context(sse_client(cfg["url"], headers=cfg.get("headers"), httpx_client_factory=local_http))
                else:
                    http_client = await stack.enter_async_context(local_http(headers=cfg.get("headers")))
                    streams = await stack.enter_async_context(streamable_http_client(cfg["url"], http_client=http_client))
                client = await stack.enter_async_context(ClientSession(streams[0], streams[1], read_timeout_seconds=timedelta(seconds=60)))
                info = await client.initialize()
                self.has_resources = info.capabilities.resources is not None
                self.alive = True
                # Credential values supplied by the export must not appear in responses.
                scrub = redactor(cfg)
                self.ready.set_result(scrub({"session_id": self.id, "connection": self.name, "server": info.serverInfo.model_dump(mode="json"), "note": "Session identity identifies this MCP connection, not an OS PID or document. Read native scene state before edits."}))
                while True:
                    operation, args, pending = await self.queue.get()
                    if pending.cancelled():
                        pending = None
                        continue
                    if operation == "tools":
                        tools = {}
                        cursor = None
                        seen = set()
                        for _ in range(100):
                            result = await client.list_tools(cursor=cursor)
                            for tool in result.tools:
                                tools[tool.name] = tool
                            cursor = result.nextCursor
                            if not cursor:
                                break
                            if cursor in seen:
                                raise ValueError("Repeated tools cursor")
                            seen.add(cursor)
                        else:
                            raise ValueError("Too many tool pages")
                        self.tools = tools
                        value = {"session_id": self.id, "tools": [t.model_dump(mode="json") for t in tools.values()]}
                    elif operation == "call":
                        result = await client.call_tool(args["tool"], args["arguments"])
                        value = {"error": "Native tool reported failure. Its details are withheld to protect credentials; inspect Cinema 4D's local console. Partial work may have happened. Do not replay."} if result.isError else result.model_dump(mode="json")
                    elif operation == "resources":
                        resources = {}
                        cursor = None
                        seen = set()
                        for _ in range(100):
                            result = await client.list_resources(cursor=cursor)
                            for resource in result.resources:
                                resources[str(resource.uri)] = resource
                            if len(resources)>10000: raise ValueError('Resource listing exceeds 10000 entries')
                            cursor=result.nextCursor
                            if not cursor: break
                            if cursor in seen: raise ValueError('Repeated resources cursor')
                            seen.add(cursor)
                        else: raise ValueError('Too many resource pages')
                        self.resources=resources
                        value={'session_id':self.id,'resources':[r.model_dump(mode='json') for r in resources.values()], 'coverage':'Concrete resources advertised by selected server; URI templates are not expanded.'}
                    elif operation == "read_resource":
                        value=(await client.read_resource(AnyUrl(args['uri']))).model_dump(mode='json')
                    else:
                        raise ValueError("Unsupported operation")
                    if not pending.done():
                        pending.set_result(scrub(value))
                    pending = None
        except BaseException:
            # Never expose native exceptions, URLs, argv or environment values.
            if not self.ready.done():
                self.ready.set_result({"error": "Native connection failed; verify Cinema 4D is running, MCP is enabled, and the exported config is current"})
            if pending and not pending.done():
                pending.set_result({"error": "Native session failed; operation outcome may be unknown. Do not retry automatically."})
        finally:
            self.alive = False
            while not self.queue.empty():
                _, _, future = self.queue.get_nowait()
                if not future.done():
                    future.set_result({"error": "Session closed before request completed. Do not retry automatically."})

    async def request(self, operation, args, timeout):
        if not self.alive:
            raise ValueError("Session is closed; explicitly reconnect, select and inspect the scene again")
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((operation, args, future))
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            self.alive = False
            self.task.cancel()
            return {"error": "Native request timed out; session was closed. Outcome may be unknown and execution may continue in Cinema 4D. Do not replay."}


class Manager:
    def __init__(self):
        self.sessions = {}
        self.used_requests = set()

    async def connect(self, name, authorized=False):
        if not authorized:
            raise ValueError("Explicit authorization is required to connect using the registered native config")
        cfg, kind, fingerprint = load_connection(name)
        for existing in self.sessions.values():
            if existing.name == name and existing.task and not existing.task.done():
                raise ValueError("Connection already has a live or initializing session; select it or disconnect first")
        session = NativeSession(name, fingerprint)
        self.sessions[session.id] = session
        session.task = asyncio.create_task(session.run(cfg, kind))
        try:
            return await asyncio.wait_for(asyncio.shield(session.ready), 20)
        except asyncio.TimeoutError:
            session.task.cancel()
            return {"error": "Native initialization timed out; no automatic reconnect"}

    def select(self, session_id):
        session = self.sessions.get(session_id)
        if not session or not session.alive:
            raise ValueError("Unknown or closed session; explicitly connect and select a live session")
        _, _, fingerprint = load_connection(session.name)
        if fingerprint != session.fingerprint:
            raise ValueError("Session configuration changed; disconnect and explicitly reconnect")
        return session

    async def tools(self, session_id):
        return await self.select(session_id).request("tools", {}, 20)

    async def resources(self, session_id):
        session=self.select(session_id)
        if not session.has_resources:
            return {'session_id':session_id,'supported':False,'resources':[],'note':'Selected native server did not advertise resources capability'}
        return await session.request('resources',{},20)

    async def read_resource(self, session_id, uri):
        session=self.select(session_id)
        if not isinstance(uri,str) or uri not in session.resources:
            raise ValueError('List resources in this session first and select an exact advertised URI; arbitrary paths/URLs and templates are not accepted')
        return await session.request('read_resource',{'uri':uri},30)

    async def call(self, session_id, tool, arguments, request_id, authorized=False, timeout=30):
        session = self.select(session_id)
        if not authorized:
            raise ValueError("Every native call requires authorization; native annotations do not prove it is read-only")
        if tool not in session.tools:
            raise ValueError("Discover tools in this session first and use an exact advertised name")
        if not isinstance(arguments, dict) or not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise ValueError("Provide an arguments object and a unique request_id of 8-128 characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 1 <= timeout <= 120:
            raise ValueError("Timeout must be 1-120 seconds")
        if request_id in self.used_requests:
            raise ValueError("Request ID was already submitted; never replay it")
        validate_arguments(session.tools[tool].inputSchema, arguments)
        # Retain failed/timeout IDs too; a native operation may already have happened.
        self.used_requests.add(request_id)
        return await session.request("call", {"tool": tool, "arguments": arguments}, timeout)

    async def disconnect(self, session_id):
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError("Unknown session")
        session.alive = False
        session.task.cancel()
        await asyncio.gather(session.task, return_exceptions=True)
        return {"disconnected": session_id, "note": "This does not stop the native Cinema 4D server or undo submitted work"}

    def status(self):
        return [{"session_id": s.id, "connection": s.name, "connected": s.alive, "discovered_tools": len(s.tools)} for s in self.sessions.values()]
