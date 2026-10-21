"use strict";
// Only a serialized structured job crosses evalScript; there is no script/eval tool.
function createHost(evalScript) {
    function run(job) {
        const encoded = JSON.stringify(job).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
        return new Promise((resolve, reject) => evalScript("$._bubblePremiere.dispatch(" + encoded + ")", raw => {
            try {const reply=JSON.parse(raw);if(!reply.ok)throw new Error(reply.error.message);resolve(reply.data);}
            catch(error){reject(error);}
        }));
    }
    return {info:()=>run({operation:"host_info"}),dispatch:(operation,args,expires_at)=>run({operation,arguments:args,expires_at})};
}
if(typeof module!=="undefined")module.exports={createHost};
