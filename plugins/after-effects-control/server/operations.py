"""ExtendScript operations with explicit project-state and native-session guards."""
import json


BODY = r'''
(function(){
var q=REQUEST, result, f, layerBudget=10000;
function encode(v){if(v===null||v===undefined)return 'null';if(typeof v==='string')return '"'+v.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n').replace(/\t/g,'\\t').replace(/[\x00-\x1f]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);})+'"';if(typeof v==='number')return isFinite(v)?String(v):'null';if(typeof v==='boolean')return String(v);var a=[],k;if(v instanceof Array){for(k=0;k<v.length;k++)a.push(encode(v[k]));return '['+a.join(',')+']';}for(k in v)if(v.hasOwnProperty(k))a.push(encode(k)+':'+encode(v[k]));return '{'+a.join(',')+'}';}
function state(){if(app.project.numItems>10000)throw Error('Project exceeds 10000 item inspection limit');var ids=[];for(var i=1;i<=app.project.numItems;i++){var x=app.project.item(i);ids.push([x.id,x.name,x.typeName]);}return {path:app.project.file?app.project.file.fsName:null,revision:app.project.revision,root_id:app.project.rootFolder.id,items:ids};}
function sameState(a,b){return b&&a.path===b.path&&a.revision===b.revision&&a.root_id===b.root_id&&encode(a.items)===encode(b.items);}
function comp(id){var c=app.project.itemByID(id);if(!(c instanceof CompItem))throw Error('Selected item is not a composition');return c;}
function layer(c,id){for(var i=1;i<=c.numLayers;i++)if(c.layer(i).id===id)return c.layer(i);throw Error('Layer ID no longer exists');}
function itemInfo(x){if(!x)throw Error('Item no longer exists');var o={item_id:x.id,name:x.name,type:x.typeName};if(x instanceof CompItem){layerBudget-=x.numLayers;if(layerBudget<0)throw Error('Inspection exceeds 10000 layer limit');o.width=x.width;o.height=x.height;o.duration=x.duration;o.frame_rate=x.frameRate;o.layers=[];for(var i=1;i<=x.numLayers;i++){var l=x.layer(i);o.layers.push({layer_id:l.id,index:i,name:l.name,locked:l.locked});}}if(x instanceof FootageItem)o.path=x.file?x.file.fsName:null;return o;}
try{
 if(new Date().getTime()>q.expires_at)throw Error('Request expired before execution');
 if(parseInt(app.version,10)<26)throw Error('After Effects 26+ required');
 if(app.preferences.getPrefAsLong('Main Pref Section','Pref_SCRIPTING_FILE_NETWORK_SECURITY')!==1)throw Error('Enable Allow Scripts to Write Files and Access Network manually in After Effects preferences');
 if(!app.project)throw Error('No project is available');
 var key='BubbleAE_'+q.server_id, s=$.global[key];
 if(q.operation==='project_info'){
   if(!s){s={token:q.token,project:app.project};$.global[key]=s;}
   if(s.token!==q.token)throw Error('Session token mismatch');
   s.project=app.project;
 }else{
   if(!s||s.token!==q.token)throw Error('Native session changed; read project info again');
   if(s.project!==app.project)throw Error('Project object changed; read project info again');
   if(!sameState(state(),q.expected_project_state))throw Error('Project state changed; read project info again');
 }
 var data={}, a=q.args||{}, c,l,x;
 if(q.operation==='project_info'){state();data.version=app.version;data.items=[];for(var i=1;i<=app.project.numItems;i++)data.items.push(itemInfo(app.project.item(i)));}
 else if(q.operation==='inspect_item')data=itemInfo(app.project.itemByID(a.item_id));
 else {
  if(new Date().getTime()>q.expires_at)throw Error('Request expired before mutation');
  app.beginUndoGroup('Bubble After Effects');
  try{
   if(q.operation==='create_comp'){x=app.project.items.addComp(a.name,a.width,a.height,1,a.duration,a.frame_rate);data=itemInfo(x);}
   else if(q.operation==='import_file'){var input=new File(a.path);if(!input.exists)throw Error('Input file no longer exists');x=app.project.importFile(new ImportOptions(input));data=itemInfo(x);}
   else if(q.operation==='add_layer'){
    c=comp(a.comp_id);
    if(a.kind==='text')l=c.layers.addText(a.text);
    else if(a.kind==='solid')l=c.layers.addSolid(a.color,a.name,c.width,c.height,1,c.duration);
    else {x=app.project.itemByID(a.item_id);if(!(x instanceof FootageItem||x instanceof CompItem))throw Error('Source must be footage or comp');if(x===c)throw Error('Cannot add a comp to itself');l=c.layers.add(x);}
    data={layer_id:l.id,name:l.name};
   }else if(q.operation==='set_transform'){
    c=comp(a.comp_id);l=layer(c,a.layer_id);if(l.locked)throw Error('Layer is locked');var t=l.property('ADBE Transform Group');
    var pairs=[['position','ADBE Position'],['scale','ADBE Scale'],['opacity','ADBE Opacity'],['rotation','ADBE Rotate Z']];
    for(var j=0;j<pairs.length;j++)if(a[pairs[j][0]]!==null){var p=t.property(pairs[j][1]);if(!p||p.numKeys||p.expressionEnabled||(p.isSeparationLeader&&p.dimensionsSeparated))throw Error('Animated, expression-driven or separated transform requires explicit JSX');if(a[pairs[j][0]] instanceof Array && a[pairs[j][0]].length!==p.value.length)throw Error('Transform dimensions do not match layer');}
    for(var j=0;j<pairs.length;j++)if(a[pairs[j][0]]!==null){if(new Date().getTime()>q.expires_at)throw Error('Request expired; earlier transforms may have applied');t.property(pairs[j][1]).setValue(a[pairs[j][0]]);}
    data={layer_id:l.id};
   }else if(q.operation==='save_project'){
    var dest=new File(a.path);if(dest.exists&&!a.overwrite)throw Error('Destination exists; explicit overwrite required');app.project.save(dest);data={path:app.project.file.fsName};
   }else if(q.operation==='execute_script'){data={result:String(eval(a.script))};}
   else throw Error('Unknown operation');
  }finally{app.endUndoGroup();}
 }
 result={ok:true,request_id:q.request_id,data:data,project_state:state()};
}catch(e){result={ok:false,request_id:q.request_id,error:{code:'host_error',message:String(e),line:e.line||null}};}
try{var output=encode(result);if(output.length>2000000)output=encode({ok:false,request_id:q.request_id,error:{code:'response_too_large',message:'Response exceeds size limit; a write may already have completed. Inspect state; do not automatically retry.'}});f=new File(q.response_path);f.encoding='UTF-8';if(f.open('w')){f.write(output);f.close();}}catch(ignore){}
})();
'''


def script(request):
    return BODY.replace('REQUEST', json.dumps(request, ensure_ascii=True, allow_nan=False), 1)
