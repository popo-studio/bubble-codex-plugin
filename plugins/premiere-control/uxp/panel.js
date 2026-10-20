"use strict";
const uxp = require("uxp");
const adapter = require("./host.js").createHost(require("premierepro"), uxp.host.version);
const transport = require("./transport.js").createTransport(adapter, text => {
    document.getElementById("status").textContent = text;
});
document.getElementById("connect").addEventListener("click", async () => {
    try {
        const input = document.getElementById("code");
        const code = input.value;
        input.value = "";
        await transport.connect(code);
    } catch (error) {
        document.getElementById("status").textContent = String(error.message || error);
    }
});
document.getElementById("disconnect").addEventListener("click", () => transport.disconnect());
uxp.entrypoints.setup({panels: {bubblePremiere: {hide() { transport.disconnect(); },
    destroy() { transport.disconnect(); }}}, plugin: {destroy() { transport.disconnect(); }}});
