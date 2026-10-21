"use strict";
const report = text => {document.getElementById("status").textContent=text;};
const host = createHost((script, done)=>window.__adobe_cep__.evalScript(script,done));
const transport = createTransport(host, report);
document.getElementById("connect").onclick=async()=>{const field=document.getElementById("code");try{await transport.connect(field.value);field.value="";}catch(e){report(String(e.message||e));}};
document.getElementById("disconnect").onclick=()=>transport.disconnect();
window.addEventListener("beforeunload",()=>transport.disconnect());
