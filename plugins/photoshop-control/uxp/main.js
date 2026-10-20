"use strict";
const {createHost} = require("./host.js");
const {createTransport} = require("./transport.js");
const host = createHost(require("photoshop"));
const report = text => { document.getElementById("status").textContent = text.replace(/^Connected: /, "已连接：").replace(/^Disconnected/, "已断开"); };
const transport = createTransport(host, report);
document.getElementById("connect").addEventListener("click", async () => {
  try {
    await transport.connect(document.getElementById("code").value);
    document.getElementById("code").value = "";
  } catch (error) { report(String(error.message || error)); }
});
document.getElementById("disconnect").addEventListener("click", () => transport.disconnect());
require("uxp").entrypoints.setup({panels:{bubblePhotoshop:{destroy(){transport.disconnect();}}}});
