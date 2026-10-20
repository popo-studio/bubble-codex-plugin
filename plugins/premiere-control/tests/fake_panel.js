// Real production transport + host adapter, with an in-memory Adobe DOM double.
const readline = require("node:readline");
const {createTransport} = require("../uxp/transport.js");
const {createHost} = require("../uxp/host.js");
const project = {guid: {toString: () => "mock-project"}, name: "hero.prproj", path: "D:/hero.prproj",
    getSequences: async () => [{guid: {toString: () => "mock-sequence"}, name: "edit"}],
    getRootItem: async () => ({getItems: async () => []}),
    importFiles: async () => true, save: async () => true};
const host = createHost({Project: {getActiveProject: async () => project}}, "25.6-mock");
const transport = createTransport(host, () => {});
readline.createInterface({input: process.stdin}).on("line", async line => {
    if (line === "stop") {await transport.disconnect(); process.exit(0);}
    try {await transport.connect(line); process.stdout.write("connected\n");}
    catch (error) {process.stderr.write(String(error.message)); process.exit(1);}
});
