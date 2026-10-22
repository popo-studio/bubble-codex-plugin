// File IPC is confined to the opted-in user's protected runtime folder.
function createBubbleAEBridge(config){
 function encode(v){if(v===null||v===undefined)return 'null';if(typeof v==='string')return '"'+v.replace(/[\\"\x00-\x1f\u2028\u2029]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);})+'"';if(typeof v==='number')return isFinite(v)?String(v):'null';if(typeof v==='boolean')return String(v);var a=[],k;if(v instanceof Array){for(k=0;k<v.length;k++)a.push(encode(v[k]));return '['+a.join(',')+']';}for(k in v)if(v.hasOwnProperty(k))a.push(encode(k)+':'+encode(v[k]));return '{'+a.join(',')+'}';}
 // Strict recursive JSON parser. IPC data is never evaluated as JavaScript.
 function parse(s){var i=0,depth=0;function ws(){while(/\s/.test(s.charAt(i))&&i<s.length)i++;}function value(){if(++depth>30)throw Error('JSON depth');ws();var c=s.charAt(i++),v,k,a;if(c==='"'){v='';while(i<s.length){c=s.charAt(i++);if(c==='"'){depth--;return v;}if(c==='\\'){c=s.charAt(i++);if(c==='u'){k=s.substr(i,4);if(!/^[0-9a-f]{4}$/i.test(k))throw Error('JSON escape');v+=String.fromCharCode(parseInt(k,16));i+=4;}else{a={'"':'"','\\':'\\','/':'/','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t'};if(!a.hasOwnProperty(c))throw Error('JSON escape');v+=a[c];}}else{if(c.charCodeAt(0)<32)throw Error('JSON string');v+=c;}}throw Error('JSON string');}if(c==='{'||c==='['){a=c==='{'?{}:[];ws();if(s.charAt(i)===(c==='{'?'}':']')){i++;depth--;return a;}while(true){if(c==='{'){ws();if(s.charAt(i)!=='"')throw Error('JSON key');k=value();if(k==='__proto__'||k==='constructor'||k==='prototype'||k==='hasOwnProperty')throw Error('JSON unsafe key');ws();if(s.charAt(i++)!==':')throw Error('JSON colon');a[k]=value();}else a.push(value());ws();k=s.charAt(i++);if(k===(c==='{'?'}':']'))break;if(k!==',')throw Error('JSON comma');}depth--;return a;}i--;var tail=s.substr(i);a=/^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(tail);if(!a)throw Error('JSON value');i+=a[0].length;depth--;return a[0]==='true'?true:a[0]==='false'?false:a[0]==='null'?null:Number(a[0]);}var out=value();ws();if(i!==s.length)throw Error('JSON trailing data');return out;}
 function read(path){var f=new File(path);if(!f.exists||f.length>1048576)throw Error('File unavailable or too large');f.encoding='UTF-8';if(!f.open('r'))throw Error('Read failed');try{return parse(f.read());}finally{f.close();}}
 function write(path,data){var text=encode(data);if(text.length>2000000)throw Error('Response too large');var f=new File(path+'.tmp');f.encoding='UTF-8';if(!f.open('w'))throw Error('Write failed');try{f.write(text);}finally{f.close();}var dest=new File(path);if(dest.exists)dest.remove();if(!f.rename(dest.name))throw Error('Publish failed');}
 function nonce(){var s='';for(var i=0;i<8;i++)s+=('0000'+Math.floor(Math.random()*65536).toString(16)).slice(-4);return s;}
 function normalized(s){return String(s).replace(/\\/g,'/').toLowerCase();}
 function enabled(){try{var r=read(config.root+'/receipt.json');return r.schema===1&&r.version==='0.3.0'&&r.enabled===true&&r.installation_id===config.installation_id&&normalized(r.profile)===normalized(config.profile)&&normalized($.getenv('LOCALAPPDATA'))===normalized(config.profile);}catch(e){return false;}}
 var sid=nonce(),token=nonce()+nonce(),base=config.root+'/hosts/'+sid,stopped=false,task=null,busy=false;
 function mkdir(p){var f=new Folder(p);if(!f.exists&&!f.create())throw Error('Cannot create runtime folder');}
 function stop(){stopped=true;if(task!==null){try{app.cancelTask(task);}catch(e){}}try{new File(base+'/heartbeat.json').remove();}catch(e){}}
 function tick(){if(stopped||busy)return;busy=true;try{
  if(!enabled()){stop();return;}if(parseInt(app.version,10)!==26)throw Error('AE 26.x required');
  if(app.preferences.getPrefAsLong('Main Pref Section','Pref_SCRIPTING_FILE_NETWORK_SECURITY')!==1)throw Error('Enable scripting file permission manually');
  mkdir(config.root+'/hosts');mkdir(base);mkdir(base+'/requests');mkdir(base+'/results');
  if(!new File(base+'/.owner.json').exists)write(base+'/.owner.json',{schema:1,session_id:sid,installation_id:config.installation_id,bridge_version:'0.3.0'});
  var p=app.project,now=new Date().getTime();write(base+'/heartbeat.json',{schema:1,session_id:sid,token:token,installation_id:config.installation_id,bridge_version:'0.3.0',version:app.version,expires_at:now+12000,project:{name:p&&p.file?p.file.name:'Untitled',path:p&&p.file?p.file.fsName:null}});
  var files=new Folder(base+'/requests').getFiles('*.json');files.sort(function(a,b){return b.modified-a.modified;});
  for(var i=0;i<Math.min(files.length,128);i++){
   var file=files[i],id=file.name.replace(/\.json$/,'');if(!/^[0-9a-f]{32}$/.test(id))continue;
   var q;try{q=read(file.fsName);}catch(e){continue;}
   if(q.request_id!==id||q.session_id!==sid||q.host_token!==token||typeof q.expires_at!=='number'||!isFinite(q.expires_at)||q.expires_at>now+125000||typeof q.server_id!=='string'||!/^[0-9a-f]{32}$/.test(q.server_id)||typeof q.token!=='string'||!/^[0-9a-f]{64}$/.test(q.token)||!(/^(project_info|inspect_item|create_comp|import_file|add_layer|set_transform|save_project|execute_script|new_project|open_project|update_comp|update_layer|duplicate_layer|remove_layer|update_text|keyframes|set_keyframe|remove_keyframe|layer_effects|add_effect|render_queue|queue_comp)$/.test(q.operation)))continue;
   if(!file.rename(id+'.running'))continue;
   var result;
   if(!enabled()||new Date().getTime()>=q.expires_at)result={ok:false,error:{code:'expired',message:'Request expired or installation revoked before execution'}};
   else result=bubbleExecute(q);
   result.request_id=id;
   try{write(base+'/results/'+id+'.json',result);}catch(e){try{write(base+'/results/'+id+'.json',{ok:false,request_id:id,error:{code:'result_failed',message:'Operation may have completed; no automatic retry'}});}catch(ignore){}}
   file.remove();break;
  }
 }catch(e){}finally{busy=false;}}
 function start(){if(app.isRenderEngine||app.isWatchFolder||!enabled())return;task=app.scheduleTask('$.global.BubbleAEBridge.tick()',500,true);}
 return {tick:tick,start:start,stop:stop,session_id:sid};
}
