"use strict";
// Read-only discovery in the current Windows user's profile. Never accept URLs or arbitrary directories.
function createDiscoveryReader(fs,path,env,extensionPath){
    const base=env.LOCALAPPDATA;
    const appdata=env.APPDATA;
    if(!base||!appdata||!path.isAbsolute(base)||!path.isAbsolute(appdata))throw Error("Current user profile unavailable");
    const root=path.join(base,"Bubble","Codex","premiere","discovery");
    const target=path.join(appdata,"Adobe","CEP","extensions","com.popostudio.bubble.premiere");
    const receipt=path.join(path.dirname(target),"com.popostudio.bubble.premiere.bubble-install.json");
    function safe(file){
        let current=path.resolve(file);
        while(true){if(fs.existsSync(current)&&fs.lstatSync(current).isSymbolicLink())throw Error("Discovery path is a link");const parent=path.dirname(current);if(parent===current)break;current=parent;}
        if(fs.existsSync(file)&&path.resolve(fs.realpathSync(file)).toLowerCase()!==path.resolve(file).toLowerCase())throw Error("Discovery path is redirected");
    }
    function readJSON(file){safe(file);if(fs.statSync(file).size>65536)throw Error("Record too large");return JSON.parse(fs.readFileSync(file,"utf8"));}
    return function readRecords(){
        // Removing/replacing the managed receipt revokes already loaded background code.
        safe(target);safe(receipt);
        if(!fs.existsSync(target)||!fs.existsSync(receipt)||path.resolve(extensionPath).toLowerCase()!==path.resolve(target).toLowerCase())return [];
        const owner=readJSON(receipt);
        if(owner.plugin_id!=="com.popostudio.bubble.premiere"||owner.version!=="0.5.0"||path.resolve(owner.target).toLowerCase()!==path.resolve(target).toLowerCase())return [];
        safe(root);if(!fs.existsSync(root))return [];
        const rows=[];
        const candidates=fs.readdirSync(root).filter(name=>/^[0-9a-f-]{36}\.json$/.test(name)).map(name=>{
            try{const file=path.join(root,name);safe(file);return {name,modified:fs.statSync(file).mtimeMs};}catch(_){return null;}
        }).filter(Boolean).sort((a,b)=>b.modified-a.modified).slice(0,128);
        for(const candidate of candidates){const name=candidate.name;
            if(!/^[0-9a-f-]{36}\.json$/.test(name))continue;
            try{const item=readJSON(path.join(root,name));if(item.broker_id+".json"===name)rows.push(item);}catch(_){}
        }
        return rows;
    };
}
if(typeof module!=="undefined")module.exports={createDiscoveryReader};
