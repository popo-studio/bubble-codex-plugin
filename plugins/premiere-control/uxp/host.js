"use strict";
// Premiere 25.6+ public UXP DOM only. No QE, ExtendScript, eval, or hidden APIs.
function createHost(ppro, hostVersion) {
    const id = value => value && value.toString ? value.toString() : "";
    function deadline(expires) {
        if (!Number.isFinite(expires) || Date.now() >= expires * 1000)
            throw new Error("Request expired before host operation");
    }
    async function active(expected) {
        const project = await ppro.Project.getActiveProject();
        if (!project) throw new Error("No active project");
        if (typeof expected !== "string" || !expected || id(project.guid) !== expected)
            throw new Error("Project selection changed or missing project_id; list sessions again");
        return project;
    }
    async function info() {
        const project = await ppro.Project.getActiveProject();
        return {app: "premiere", version: hostVersion, targets: project ? [
            {id: id(project.guid), name: project.name, path: project.path || ""}
        ] : [], scope: "Only the active project in this paired panel is advertised"};
    }
    async function items(project, expires, maximum) {
        const result = [];
        const queue = [await project.getRootItem()];
        while (queue.length) {
            deadline(expires);
            const folder = queue.shift();
            const children = await folder.getItems();
            for (const item of children) {
                deadline(expires);
                if (result.length >= maximum) return {items: result, truncated: true};
                const row = {id: String(await item.getId()), name: item.name, path: null, offline: null};
                let bin = null;
                try { bin = ppro.FolderItem.cast(item); } catch (_) {}
                if (bin) {
                    row.kind = "bin";
                    queue.push(bin);
                } else {
                    try {
                        const clip = ppro.ClipProjectItem.cast(item);
                        if (!clip) throw new Error("Not a media clip");
                        row.kind = await clip.isSequence() ? "sequence" : "media";
                        if (row.kind === "media") {
                            row.path = await clip.getMediaFilePath();
                            row.offline = await clip.isOffline();
                        }
                    } catch (error) {
                        row.kind = "unverified";
                        row.error = String(error.message || error);
                    }
                }
                result.push(row);
            }
        }
        return {items: result, truncated: false};
    }
    async function findItem(project, wanted, expires) {
        if (typeof wanted !== "string" || !wanted) throw new Error("item_id required");
        const queue = [await project.getRootItem()];
        let visited = 0;
        while (queue.length) {
            const children = await queue.shift().getItems();
            for (const item of children) {
                deadline(expires);
                if (++visited > 10000) throw new Error("Item search limit exceeded");
                if (String(await item.getId()) === wanted) return item;
                try { const folder = ppro.FolderItem.cast(item); if (folder) queue.push(folder); } catch (_) {}
            }
        }
        throw new Error("Item no longer exists in selected project");
    }
    async function dispatch(operation, args, expires) {
        deadline(expires);
        args = args || {};
        if (operation === "status") return await info();
        const project = await active(args.project_id);
        deadline(expires);
        if (operation === "project_info") {
            const sequences = await project.getSequences();
            return {id: id(project.guid), name: project.name, path: project.path,
                sequences: sequences.slice(0, 1000).map(s => ({id: id(s.guid), name: s.name})),
                truncated: sequences.length > 1000};
        }
        if (operation === "inspect_media") return await items(project, expires, 1000);
        if (operation === "import_files") {
            if (!Array.isArray(args.paths) || !args.paths.length || args.paths.length > 100 ||
                args.paths.some(p => typeof p !== "string" || !p || p.indexOf("\0") >= 0))
                throw new Error("Supply 1–100 valid media paths");
            const root = await project.getRootItem();
            await active(args.project_id);
            deadline(expires);
            return {imported: await project.importFiles(args.paths, true, root, false),
                note: "Project modified but not saved"};
        }
        if (operation === "relink_media") {
            if (typeof args.path !== "string" || !args.path || args.path.indexOf("\0") >= 0)
                throw new Error("New media path required");
            const item = await findItem(project, args.item_id, expires);
            const clip = ppro.ClipProjectItem.cast(item);
            if (!clip || !await clip.canChangeMediaPath()) throw new Error("Item cannot be relinked");
            await active(args.project_id);
            deadline(expires);
            return {relinked: await clip.changeMediaFilePath(args.path, false),
                note: "This Adobe operation is not undoable. Project has not been saved."};
        }
        if (operation === "save_project") {
            if (!project.path) throw new Error("Save an initial project file through Premiere first");
            await active(args.project_id);
            deadline(expires);
            return {saved: await project.save()};
        }
        throw new Error("Unsupported operation; arbitrary remote JavaScript is not supported");
    }
    return {info, dispatch};
}
module.exports = {createHost};
