const test = require("node:test");
const assert = require("node:assert/strict");
const {createHost} = require("../uxp/host.js");
function fixture() {
    let calls = [];
    const clip = {name: "clip", getId: async () => "item-1", isSequence: async () => false,
        getMediaFilePath: async () => "C:/a.mov", isOffline: async () => true,
        canChangeMediaPath: async () => true,
        changeMediaFilePath: async (path, override) => {calls.push(["relink", path, override]); return true;}};
    const project = {guid: {toString: () => "project-1"}, name: "shot.prproj", path: "C:/shot.prproj",
        getSequences: async () => [{guid: {toString: () => "seq-1"}, name: "edit"}],
        getRootItem: async () => ({getItems: async () => [clip]}),
        importFiles: async (...args) => {calls.push(["import", ...args]); return true;},
        save: async () => {calls.push(["save"]); return true;}};
    const api = {Project: {getActiveProject: async () => project},
        FolderItem: {cast: () => null}, ClipProjectItem: {cast: item => item}};
    return {project, clip, api, calls, host: createHost(api, "25.6")};
}
const expiry = () => Date.now() / 1000 + 10;
test("advertises active project with opaque GUID", async () => {
    const x = fixture(); assert.equal((await x.host.info()).targets[0].id, "project-1");
});
test("rejects switched project before mutation", async () => {
    const x = fixture();
    await assert.rejects(x.host.dispatch("save_project", {project_id: "other"}, expiry()), /selection changed/);
    assert.equal(x.calls.length, 0);
});
test("expired command does not run", async () => {
    const x = fixture();
    await assert.rejects(x.host.dispatch("save_project", {project_id: "project-1"}, 1), /expired/);
    assert.equal(x.calls.length, 0);
});
test("media report uses Adobe offline state", async () => {
    const x = fixture();
    const result = await x.host.dispatch("inspect_media", {project_id: "project-1"}, expiry());
    assert.equal(result.items[0].offline, true); assert.equal(result.truncated, false);
});
test("media errors remain explicitly unverified", async () => {
    const x = fixture(); x.clip.isOffline = async () => {throw Error("host busy");};
    const result = await x.host.dispatch("inspect_media", {project_id: "project-1"}, expiry());
    assert.equal(result.items[0].offline, null); assert.equal(result.items[0].kind, "unverified");
});
test("import preserves root target and does not save", async () => {
    const x = fixture();
    await x.host.dispatch("import_files", {project_id: "project-1", paths: ["C:/new.mov"]}, expiry());
    assert.equal(x.calls.length, 1); assert.equal(x.calls[0][0], "import"); assert.equal(x.calls[0][2], true);
});
test("relink retains Adobe compatibility checks", async () => {
    const x = fixture();
    await x.host.dispatch("relink_media", {project_id: "project-1", item_id: "item-1", path: "C:/new.mov"}, expiry());
    assert.deepEqual(x.calls[0], ["relink", "C:/new.mov", false]);
});
test("unknown item cannot relink", async () => {
    const x = fixture();
    await assert.rejects(x.host.dispatch("relink_media", {project_id: "project-1", item_id: "wrong", path: "C:/a"}, expiry()), /no longer exists/);
    assert.equal(x.calls.length, 0);
});
test("no remote arbitrary script execution", async () => {
    const x = fixture();
    await assert.rejects(x.host.dispatch("execute_script", {project_id: "project-1", code: "evil()"}, expiry()), /Unsupported/);
});
