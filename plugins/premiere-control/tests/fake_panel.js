// Production automatic manager/reader/transport with a simulated Adobe DOM.
const readline=require("node:readline"),fs=require("node:fs"),path=require("node:path");
const {createTransport}=require("../cep/transport"),{createHost}=require("../cep/host"),{createAutoManager}=require("../cep/auto"),{createDiscoveryReader}=require("../cep/discovery"),{fixture}=require("./mock_host");
let manager,timer,announced=false;
readline.createInterface({input:process.stdin}).on("line",async line=>{
 if(line==="stop"){clearInterval(timer);if(manager)await manager.close();process.exit(0);}
 try{const config=JSON.parse(line);const reader=createDiscoveryReader(fs,path,config,config.target);manager=createAutoManager(createHost(fixture().evalScript),reader,a=>createTransport(a,()=>{}));
 const tick=async()=>{await manager.scan();if(manager.count()&&!announced){announced=true;process.stdout.write("connected\n");}};
 timer=setInterval(tick,100);await tick();}catch(e){process.stderr.write(String(e.message));process.exit(1);}
});
