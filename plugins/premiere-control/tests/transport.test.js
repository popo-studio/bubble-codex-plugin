const test = require("node:test");
const assert = require("node:assert/strict");
const {createTransport} = require("../cep/transport.js");
const code = "bubble-premiere:1:33333:" + "a".repeat(43);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
test("expired queued command never reaches host adapter", async () => {
    let ran = 0, result;
    const mockFetch = async (url, options) => {
        const body = JSON.parse(options.body);
        let data = null;
        if (url.endsWith("/register")) data = {session_id: "one"};
        if (url.endsWith("/poll")) data = {request_id: "job", operation: "save", arguments: {}, expires_at: 1};
        if (url.endsWith("/result")) result = body.response;
        return {ok: true, json: async () => ({ok: true, data})};
    };
    const transport = createTransport({info: async () => ({}), dispatch: async () => ran++}, () => {}, mockFetch);
    await transport.connect(code);
    await sleep(20);
    await transport.disconnect();
    assert.equal(ran, 0); assert.equal(result.ok, false);
});
test("transport failure does not replay a write", async () => {
    let ran = 0, polls = 0;
    const mockFetch = async url => {
        if (url.endsWith("/result")) throw Error("lost response");
        const data = url.endsWith("/register") ? {session_id: "one"} :
            url.endsWith("/poll") ? (polls++, {request_id: "job", operation: "save", arguments: {}, expires_at: Date.now()/1000+2}) : null;
        return {ok: true, json: async () => ({ok: true, data})};
    };
    const transport = createTransport({info: async () => ({}), dispatch: async () => ran++}, () => {}, mockFetch);
    await transport.connect(code); await sleep(20); await transport.disconnect();
    assert.equal(ran, 1); assert.equal(polls, 1);
});
test("disconnect while polling cancels delivered but unstarted command", async () => {
    let ran = 0, resolvePoll;
    const mockFetch = async url => {
        if (url.endsWith("/poll")) return new Promise(resolve => {resolvePoll = resolve;});
        return {ok: true, json: async () => ({ok: true, data: {session_id: "one"}})};
    };
    const transport = createTransport({info: async () => ({}), dispatch: async () => ran++}, () => {}, mockFetch);
    await transport.connect(code); await sleep(5); await transport.disconnect();
    resolvePoll({ok: true, json: async () => ({ok: true, data: {request_id: "job", expires_at: Date.now()/1000+2}})});
    await sleep(5); assert.equal(ran, 0);
});
test("connection code cannot route off loopback", async () => {
    let calls = 0;
    const transport = createTransport({}, () => {}, async () => calls++);
    await assert.rejects(transport.connect("http://evil.test"));
    assert.equal(calls, 0);
});
test("superseded registration is unregistered and cannot steal new connection", async () => {
    const pending = [], removed = [], statuses = [];
    const mockFetch = async (url, options) => {
        if (url.endsWith("/register")) return new Promise(resolve => pending.push(resolve));
        if (url.endsWith("/unregister")) removed.push(JSON.parse(options.body).session_id);
        return {ok: true, json: async () => ({ok: true, data: null})};
    };
    const transport = createTransport({info: async () => ({})}, text => statuses.push(text), mockFetch);
    const first = transport.connect(code); await sleep(5);
    const second = transport.connect(code); await sleep(5);
    pending[1]({ok: true, json: async () => ({ok: true, data: {session_id: "new"}})});
    await second;
    pending[0]({ok: true, json: async () => ({ok: true, data: {session_id: "old"}})});
    await first; await transport.disconnect();
    assert.deepEqual(removed, ["old", "new"]);
    assert.equal(statuses.includes("Connected: old"), false);
});
