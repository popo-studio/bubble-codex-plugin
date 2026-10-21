// Real CEP host source, VM Adobe DOM double, production transport.
const readline=require("node:readline"),{createTransport}=require("../cep/transport"),{createHost}=require("../cep/host"),{fixture}=require("./mock_host");
const transport=createTransport(createHost(fixture().evalScript),()=>{});
readline.createInterface({input:process.stdin}).on("line",async line=>{if(line==="stop"){await transport.disconnect();process.exit(0);}try{await transport.connect(line);process.stdout.write("connected\n");}catch(e){process.stderr.write(String(e.message));process.exit(1);}});
