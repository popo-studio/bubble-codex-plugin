"use strict";
(function(){
    // CEP's bundled Node runtime is used only for current-user profile discovery.
    const node=window.cep_node || cep_node;
    const fs=node.require("fs"),path=node.require("path");
    const extensionPath=decodeURIComponent(window.location.pathname).replace(/^\/(?:([A-Za-z]):)/,"$1:");
    const readRecords=createDiscoveryReader(fs,path,node.process.env,path.dirname(extensionPath));
    const host=createHost((script,done)=>window.__adobe_cep__.evalScript(script,done));
    const manager=createAutoManager(host,readRecords,adapter=>createTransport(adapter,()=>{}));
    const timer=setInterval(()=>manager.scan(),1000);
    manager.scan();
    window.addEventListener("beforeunload",()=>{clearInterval(timer);manager.close();});
})();
