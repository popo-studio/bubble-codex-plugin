"use strict";
// No eval or dynamic code: authorized Photoshop action descriptors use batchPlay.
function createHost(ps, now) {
  now = now || (() => Date.now() / 1000);
  function checkedExpiry(expiresAt) {
    if (!Number.isFinite(expiresAt) || now() >= expiresAt) throw new Error("Request expired before execution; no automatic retry");
  }
  function row(doc) {
    let path = null;
    try { path = doc.path || null; } catch (_) { /* Unsaved documents have no path. */ }
    return {id: doc.id, name: doc.name, path, modified: !doc.saved, width: doc.width,
      height: doc.height, resolution: doc.resolution, mode: String(doc.mode)};
  }
  async function info() {
    const documents = Array.from(ps.app.documents).map(row);
    return {app: "photoshop", version: ps.app.version, host_pid: null, targets: documents,
      documents, active_document_id: documents.length ? ps.app.activeDocument.id : null};
  }
  function documentById(id) {
    if (!Number.isInteger(id) || id <= 0) throw new Error("An explicit positive document_id is required");
    const doc = Array.from(ps.app.documents).find(d => d.id === id);
    if (!doc) throw new Error("Selected document is no longer open");
    return doc;
  }
  function inspect(doc) {
    let depthTruncated = false;
    const layers = [], pending = Array.from(doc.layers).reverse().map(layer => ({layer, parent_id: null, depth: 0}));
    while (pending.length && layers.length < 2000) {
      const item = pending.pop(), layer = item.layer;
      layers.push({id: layer.id, parent_id: item.parent_id, name: layer.name,
        kind: String(layer.kind), visible: layer.visible, locked: layer.locked});
      if (item.depth >= 100 && layer.layers && layer.layers.length) depthTruncated = true;
      if (item.depth < 100 && layer.layers) {
        for (let i = layer.layers.length - 1; i >= 0; --i) pending.push({layer:layer.layers[i], parent_id:layer.id, depth:item.depth+1});
      }
    }
    return {document: row(doc), layers, truncated: depthTruncated || pending.length > 0,
      dependency_check: "not_performed", note: "Layer inventory only. Linked smart object paths, missing fonts and file dependencies are not validated."};
  }
  async function dispatch(operation, args, expiresAt) {
    {
      checkedExpiry(expiresAt); args = args || {};
      if (operation === "status" || operation === "scene_info") return await info();
      if (operation === "inspect_scene") return inspect(documentById(args.document_id));
      if (operation !== "batch_play") throw new Error("Unsupported operation");
      documentById(args.document_id);
      if (!Array.isArray(args.commands) || !args.commands.length || args.commands.length > 100 ||
          args.commands.some(c => !c || typeof c !== "object" || Array.isArray(c) || typeof c._obj !== "string")) {
        throw new Error("commands must contain 1-100 Photoshop action descriptors with _obj");
      }
      const result = await ps.core.executeAsModal(async context => {
        checkedExpiry(expiresAt);
        documentById(args.document_id);
        if (context.isCancelled) throw new Error("User cancelled");
        if (ps.app.activeDocument.id !== args.document_id) throw new Error("Active document changed; select the intended document in Photoshop and request again");
        // Target check is a precondition, not a sandbox: descriptors can act on other documents/application state.
        return await ps.action.batchPlay(args.commands, {});
      }, {commandName:"Bubble Photoshop authorized action", timeOut:1});
      if (Array.isArray(result) && result.some(r => r && r._obj === "error")) {
        throw new Error("Photoshop reported an action error; partial changes may exist. Do not retry automatically. " + JSON.stringify(result));
      }
      return result;
    }
  }
  return {info, dispatch};
}
module.exports = {createHost};
