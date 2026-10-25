
function bubbleExecute(q){
var result, layerBudget=10000;
function encode(v){if(v===null||v===undefined)return 'null';if(typeof v==='string')return '"'+v.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n').replace(/\t/g,'\\t').replace(/[\x00-\x1f]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);})+'"';if(typeof v==='number')return isFinite(v)?String(v):'null';if(typeof v==='boolean')return String(v);var a=[],k;if(v instanceof Array){for(k=0;k<v.length;k++)a.push(encode(v[k]));return '['+a.join(',')+']';}for(k in v)if(v.hasOwnProperty(k))a.push(encode(k)+':'+encode(v[k]));return '{'+a.join(',')+'}';}
function state(){if(app.project.numItems>10000)throw Error('Project exceeds 10000 item inspection limit');var ids=[];for(var i=1;i<=app.project.numItems;i++){var x=app.project.item(i);ids.push([x.id,x.name,x.typeName]);}return {path:app.project.file?app.project.file.fsName:null,revision:app.project.revision,root_id:app.project.rootFolder.id,items:ids};}
function sameState(a,b){return b&&a.path===b.path&&a.revision===b.revision&&a.root_id===b.root_id&&encode(a.items)===encode(b.items);}
function comp(id){var c=app.project.itemByID(id);if(!(c instanceof CompItem))throw Error('Selected item is not a composition');return c;}
function layer(c,id){for(var i=1;i<=c.numLayers;i++)if(c.layer(i).id===id)return c.layer(i);throw Error('Layer ID no longer exists');}
function itemInfo(x){if(!x)throw Error('Item no longer exists');var o={item_id:x.id,name:x.name,type:x.typeName,parent_folder_id:x.parentFolder?x.parentFolder.id:null};if(x instanceof CompItem){layerBudget-=x.numLayers;if(layerBudget<0)throw Error('Inspection exceeds 10000 layer limit');o.width=x.width;o.height=x.height;o.duration=x.duration;o.frame_rate=x.frameRate;o.layers=[];for(var i=1;i<=x.numLayers;i++){var l=x.layer(i);o.layers.push({layer_id:l.id,index:i,name:l.name,locked:l.locked,parent_layer_id:l.parent?l.parent.id:null,start_time:l.startTime,in_point:l.inPoint,out_point:l.outPoint});}}if(x instanceof FootageItem)o.path=x.file?x.file.fsName:null;return o;}
try{
 if(new Date().getTime()>q.expires_at)throw Error('Request expired before execution');
 if(parseInt(app.version,10)!==26)throw Error('After Effects 26.x required');
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
  var undoOpened=q.operation!=='new_project'&&q.operation!=='open_project';if(undoOpened)app.beginUndoGroup('Bubble After Effects');
  try{
   function finite(v,min,max){if(typeof v!=='number'||!isFinite(v)||v<min||v>max)throw Error('Invalid numeric range');return v;}
   function layerInfo(v){return {layer_id:v.id,index:v.index,name:v.name,enabled:v.enabled,solo:v.solo,shy:v.shy,locked:v.locked};}
   function transformProperty(c,l,key){var names={position:'ADBE Position',scale:'ADBE Scale',opacity:'ADBE Opacity',rotation:'ADBE Rotate Z'};if(!names.hasOwnProperty(key))throw Error('Unsupported transform property');var p=l.property('ADBE Transform Group').property(names[key]);if(!p||(p.isSeparationLeader&&p.dimensionsSeparated))throw Error('Separated transform property unsupported');return p;}
   if(q.operation==='new_project'||q.operation==='open_project'){
    if(app.project.dirty)throw Error('Current project has unsaved changes; save or close it yourself first');
    if((app.project.file||app.project.numItems)&&!a.close_clean_current)throw Error('Explicit close_clean_current required for replacing a clean nonempty project');
    var input=null;if(q.operation==='open_project'){if(typeof a.path!=='string'||!/^[A-Za-z]:[\\\/]/.test(a.path)||!/\.aep$/i.test(a.path))throw Error('Use an absolute .aep path');input=new File(a.path);if(!input.exists)throw Error('Project file missing');}
    if(new Date().getTime()>q.expires_at)throw Error('Request expired');
    var opened=input?app.open(input):app.newProject();if(!opened||opened!==app.project)throw Error("Project open/new was cancelled or failed; inspect current project");s.project=app.project;data={path:app.project.file?app.project.file.fsName:null};
   }else if(q.operation==='project_folder'){
    var root=app.project.rootFolder,dest=a.parent_folder_id===root.id?root:app.project.itemByID(a.parent_folder_id);if(!(dest instanceof FolderItem))throw Error('Destination must be a project folder');
    if(a.action==='create'){if(typeof a.name!=='string'||!a.name.replace(/\s/g,'')||a.name.length>255)throw Error('Folder name must be 1-255 characters');for(var j=1;j<=app.project.numItems;j++){var child=app.project.item(j);if(child.parentFolder===dest&&child.name===a.name)throw Error('Destination already contains that name');}x=app.project.items.addFolder(a.name);x.parentFolder=dest;data=itemInfo(x);}
    else if(a.action==='move'){x=app.project.itemByID(a.item_id);if(!x||x===root||x===dest)throw Error('Invalid item/folder move');var cursor=dest,visited=0;while(cursor&&cursor!==root){if(cursor===x)throw Error('Cannot move a folder into its descendant');if(++visited>10000)throw Error('Folder ancestry exceeds limit');cursor=cursor.parentFolder;}x.parentFolder=dest;data=itemInfo(x);}
    else throw Error('Unknown folder action');
   }else if(q.operation==='parent_layer'||q.operation==='order_layer'||q.operation==='layer_timing'){
    c=comp(a.comp_id);l=layer(c,a.layer_id);if(l.locked)throw Error('Layer is locked');
    if(q.operation==='parent_layer'){if(typeof a.keep_world!=='boolean')throw Error('keep_world must be boolean');var parent=a.parent_layer_id===null?null:layer(c,a.parent_layer_id);var cursor=parent,visited=0;while(cursor){if(cursor===l)throw Error('Parent cycle refused');if(++visited>10000)throw Error('Layer ancestry exceeds limit');cursor=cursor.parent;}if(a.keep_world)l.parent=parent;else if(parent)l.setParentWithJump(parent);else l.setParentWithJump();data={layer_id:l.id,parent_layer_id:l.parent?l.parent.id:null,keep_world:a.keep_world};}
    else if(q.operation==='order_layer'){var relative=layer(c,a.relative_layer_id);if(relative===l)throw Error('Choose a different relative layer');if(a.placement!=='before'&&a.placement!=='after')throw Error('Invalid placement');if(a.placement==='before')l.moveBefore(relative);else l.moveAfter(relative);data=layerInfo(l);}
    else{finite(a.start_time,-10800,10800);finite(a.in_point,0,c.duration);finite(a.out_point,0,c.duration);if(a.out_point<=a.in_point)throw Error('Out point must follow in point');l.startTime=a.start_time;l.inPoint=a.in_point;l.outPoint=a.out_point;data={layer_id:l.id,start_time:l.startTime,in_point:l.inPoint,out_point:l.outPoint};}
   }else if(q.operation==='update_comp'){
    c=comp(a.comp_id);if(a.name!==null&&(typeof a.name!=='string'||!a.name.length||a.name.length>255))throw Error('Invalid comp name');
    if(a.width!==null){finite(a.width,4,30000);if(a.width%1)throw Error('Integer width required');}if(a.height!==null){finite(a.height,4,30000);if(a.height%1)throw Error('Integer height required');}if(a.duration!==null)finite(a.duration,.001,10800);if(a.frame_rate!==null)finite(a.frame_rate,1,99);
    if(a.name!==null)c.name=a.name;if(a.width!==null)c.width=a.width;if(a.height!==null)c.height=a.height;if(a.duration!==null)c.duration=a.duration;if(a.frame_rate!==null)c.frameRate=a.frame_rate;data=itemInfo(c);
   }else if(/^(update_layer|duplicate_layer|remove_layer|update_text|keyframes|set_keyframe|remove_keyframe|layer_effects|add_effect)$/.test(q.operation)){
    c=comp(a.comp_id);l=layer(c,a.layer_id);
    if(q.operation==='keyframes'||q.operation==='set_keyframe'||q.operation==='remove_keyframe'){
     var prop=transformProperty(c,l,a.property);if(prop.numKeys>1000)throw Error('Keyframe count exceeds limit');
     if(q.operation==='keyframes'){var keys=[];for(var k=1;k<=prop.numKeys;k++)keys.push({index:k,time:prop.keyTime(k),value:prop.keyValue(k)});data={layer_id:l.id,property:a.property,expression_enabled:prop.expressionEnabled,keyframes:keys};}
     else{if(l.locked||prop.expressionEnabled)throw Error('Locked or expression-driven property');finite(a.time,0,c.duration);
      if(q.operation==='remove_keyframe'){finite(a.index,1,prop.numKeys);if(a.index%1||Math.abs(prop.keyTime(a.index)-a.time)>0.000001)throw Error('Keyframe identity changed');prop.removeKey(a.index);data={removed_index:a.index};}
      else{var v=a.value,old=prop.value;if(old instanceof Array){if(!(v instanceof Array)||v.length!==old.length)throw Error('Keyframe dimensions mismatch');for(var j=0;j<v.length;j++)finite(v[j],-1000000,1000000);}else{finite(v,a.property==='opacity'?0:-1000000,a.property==='opacity'?100:1000000);}prop.setValueAtTime(a.time,v);data={time:a.time,value:v};}
     }
    }else if(q.operation==='layer_effects'||q.operation==='add_effect'){
     var effects=l.property('ADBE Effect Parade');if(!effects)throw Error('Layer does not support effects');if(effects.numProperties>1000)throw Error('Effect count exceeds limit');
     if(q.operation==='add_effect'){if(l.locked)throw Error('Layer is locked');if(typeof a.match_name!=='string'||a.match_name.length>255||!effects.canAddProperty(a.match_name))throw Error('Effect match name cannot be added');var effect=effects.addProperty(a.match_name);data={index:effect.propertyIndex,name:effect.name,match_name:effect.matchName};}
     else{var list=[];for(var j=1;j<=effects.numProperties;j++){var e=effects.property(j);list.push({index:j,name:e.name,match_name:e.matchName,enabled:e.enabled});}data={effects:list};}
    }else if(q.operation==='update_layer'){
     if(a.name!==null&&(typeof a.name!=='string'||a.name.length>255))throw Error('Invalid layer name');
     var fields=['enabled','solo','shy','locked'];for(var j=0;j<fields.length;j++)if(a[fields[j]]!==null&&typeof a[fields[j]]!=='boolean')throw Error('Boolean layer state required');
     if(l.locked&&a.locked!==false)throw Error('Layer is locked; explicit unlock required');if(a.locked===false)l.locked=false;if(a.name!==null)l.name=a.name;for(var j=0;j<fields.length;j++)if(a[fields[j]]!==null)l[fields[j]]=a[fields[j]];data=layerInfo(l);
    }else{if(l.locked)throw Error('Layer is locked');
     if(q.operation==='duplicate_layer'){var copy=l.duplicate();data=layerInfo(copy);}
     else if(q.operation==='remove_layer'){var removed=l.id;l.remove();data={removed_layer_id:removed};}
     else{var source=l.property('ADBE Text Properties');if(!source)throw Error('Layer is not text');source=source.property('ADBE Text Document');if(source.numKeys||source.expressionEnabled)throw Error('Animated text requires explicit keyframe editing');if(typeof a.text!=='string'||a.text.length>100000)throw Error('Invalid text');var td=source.value;td.text=a.text;if(a.font_size!==null)td.fontSize=finite(a.font_size,1,1296);source.setValue(td);data=layerInfo(l);}
    }
   }else if(q.operation==='render_queue'||q.operation==='queue_comp'){
    var rq=app.project.renderQueue;if(rq.rendering)throw Error('Render queue is running');if(rq.numItems>1000)throw Error('Render queue exceeds limit');
    if(q.operation==='queue_comp'){c=comp(a.comp_id);var queued=rq.items.add(c);queued.render=false;data={index:rq.numItems,comp_id:c.id,render_enabled:false};}
    else{var jobs=[];for(var j=1;j<=rq.numItems;j++){var job=rq.item(j);jobs.push({index:j,comp_id:job.comp.id,status:String(job.status),render_enabled:job.render});}data={items:jobs};}
   }else if(q.operation==='create_comp'){x=app.project.items.addComp(a.name,a.width,a.height,1,a.duration,a.frame_rate);data=itemInfo(x);}
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
  }finally{if(undoOpened)app.endUndoGroup();}
 }
 result={ok:true,request_id:q.request_id,data:data,project_state:state()};
}catch(e){result={ok:false,request_id:q.request_id,error:{code:'host_error',message:String(e),line:e.line||null}};}
return result;
}
