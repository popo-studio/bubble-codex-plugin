"use strict";
// Independent transports share one host execution queue. A disconnected job is never replayed.
function createAutoManager(host, readRecords, createConnection, now=()=>Date.now()/1000) {
    const connections=new Map();let stopped=false;let queue=Promise.resolve();let scanActive=false;
    function serial(action){const next=queue.then(action);queue=next.catch(()=>{});return next;}
    function valid(r){return r && r.schema===1 && r.plugin_id==="com.popostudio.bubble.premiere" &&
        typeof r.broker_id==="string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(r.broker_id) &&
        Number.isInteger(r.port) && r.port>0 && r.port<65536 && typeof r.token==="string" && /^[A-Za-z0-9_-]{40,100}$/.test(r.token) &&
        typeof r.expires_at==="number" && r.expires_at>now() && r.expires_at<=now()+30;}
    async function drop(id){const entry=connections.get(id);if(!entry)return;entry.alive=false;connections.delete(id);await entry.transport.disconnect();}
    async function scan(){
        if(stopped)return;
        let ownsScan=false;
        try{
            const records=await readRecords();const live=new Map();
            if(Array.isArray(records))for(const r of records)if(valid(r)&&live.size<32)live.set(r.broker_id,r);
            for(const [id,entry] of connections){const r=live.get(id);if(!r||r.port!==entry.record.port||r.token!==entry.record.token)await drop(id);}
            if(scanActive)return;
            scanActive=true;ownsScan=true;
            for(const [id,record] of live){
                if(stopped)break;
                let entry=connections.get(id);
                if(entry&&!entry.transport.connected()){await drop(id);entry=null;}
                if(entry){entry.record=record;continue;}
                entry={record,alive:true,transport:null};
                const active=entry;
                const adapter={info:()=>serial(()=>{if(!active.alive||stopped)throw Error("Connection stopped");return host.info();}),
                    dispatch:(operation,args,deadline)=>serial(async()=>{
                        if(!active.alive||stopped||active.record.expires_at<=now())throw Error("Disconnected before execution");
                        const current=await readRecords();
                        if(!Array.isArray(current)||!current.some(r=>valid(r)&&r.broker_id===id&&r.port===active.record.port&&r.token===active.record.token))
                            throw Error("Installation or broker revoked before execution");
                        if(!active.alive||stopped)throw Error("Disconnected before execution");
                        if(now()>=deadline)throw Error("Request expired in host queue");
                        return host.dispatch(operation,args,deadline);
                    })};
                active.transport=createConnection(adapter);connections.set(id,active);
                try{await active.transport.connect("bubble-premiere:1:"+record.port+":"+record.token);}
                catch(_){await drop(id);}
            }
        }catch(_){for(const id of Array.from(connections.keys()))await drop(id);}
        finally{if(ownsScan)scanActive=false;}
    }
    async function close(){stopped=true;for(const id of Array.from(connections.keys()))await drop(id);}
    return {scan,close,count:()=>connections.size};
}
if(typeof module!=="undefined")module.exports={createAutoManager};
