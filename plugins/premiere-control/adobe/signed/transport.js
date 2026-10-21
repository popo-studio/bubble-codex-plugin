"use strict";
// No eval, script injection, or automatic replay. Credentials live only in this panel.
function createTransport(adapter, report, fetchImpl) {
    const fetcher = fetchImpl || fetch;
    let state = null;
    let generation = 0;
    async function post(s, endpoint, data) {
        const response = await fetcher(s.url + endpoint, {
            method: "POST",
            headers: {Authorization: "Bearer " + s.token, "Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error("Bridge HTTP " + response.status);
        const result = await response.json();
        if (!result.ok) throw new Error((result.error || {}).message || "Bridge rejected request");
        return result.data;
    }
    async function info() {
        try { return await adapter.info(); }
        catch (error) { return {targets: [], error: String(error.message || error)}; }
    }
    async function disconnect() {
        const epoch = ++generation;
        const old = state;
        state = null;
        if (old && old.id) {
            try { await post(old, "/unregister", {session_id: old.id}); } catch (_) {}
        }
        if (generation === epoch) report("Disconnected");
    }
    async function connect(code) {
        const match = /^bubble-premiere:1:([0-9]{1,5}):([A-Za-z0-9_-]{40,100})$/.exec(code.trim());
        if (!match || +match[1] < 1 || +match[1] > 65535) throw new Error("Invalid connection code");
        const pendingDisconnect = disconnect();
        const epoch = generation;
        await pendingDisconnect;
        if (generation !== epoch) return;
        const s = {url: "http://127.0.0.1:" + match[1], token: match[2]};
        const registered = await post(s, "/register", {info: await info()});
        s.id = registered.session_id;
        if (generation !== epoch) {
            try { await post(s, "/unregister", {session_id: s.id}); } catch (_) {}
            return;
        }
        state = s;
        report("Connected: " + s.id);
        loop(s, epoch);
    }
    async function loop(s, epoch) {
        try {
            while (generation === epoch && state === s) {
                const job = await post(s, "/poll", {session_id: s.id, info: await info()});
                if (generation !== epoch || state !== s) break;
                if (job) {
                    let result;
                    try {
                        if (Date.now() >= job.expires_at * 1000) throw new Error("Request expired before execution");
                        result = {ok: true, data: await adapter.dispatch(job.operation, job.arguments, job.expires_at)};
                    } catch (error) {
                        result = {ok: false, error: {code: "host", message: String(error.message || error),
                            note: "Partial changes may exist. Do not retry automatically."}};
                    }
                    if (generation === epoch && state === s)
                        await post(s, "/result", {session_id: s.id, request_id: job.request_id, response: result});
                }
                await new Promise(resolve => setTimeout(resolve, 300));
            }
        } catch (error) {
            if (generation === epoch) {
                state = null;
                report("Disconnected: " + String(error.message || error) + ". Reconnect explicitly.");
            }
        }
    }
    return {connect, disconnect};
}
if(typeof module!=="undefined")module.exports = {createTransport};
