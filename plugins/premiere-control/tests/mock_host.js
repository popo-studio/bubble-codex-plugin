const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
function fixture(){
 const c=vm.createContext({});vm.runInContext(`
 var $={},files={"D:/mock.mov":true,"D:/hero.prproj":true};
 function File(p){this.fsName=p;this.exists=!!files[p];this.parent={exists:true};}
 function collection(rows,key){rows[key]=rows.length;return rows;}
 var clip={nodeId:"clip1",name:"source",type:1,getMediaPath:function(){return "D:/mock.mov";},isOffline:function(){return false;},isSequence:function(){return false;},canChangeMediaPath:function(){return true;},changeMediaPath:function(){return 0;}};
 var sequence={sequenceID:"mock-sequence",name:"edit",frameSizeHorizontal:1920,frameSizeVertical:1080,timebase:"10160640000",videoTracks:collection([],"numTracks"),audioTracks:collection([],"numTracks")};
 var project={documentID:"mock-project",name:"hero.prproj",path:"D:/hero.prproj",sequences:collection([sequence],"numSequences"),rootItem:{nodeId:"root",type:2,name:"root",children:collection([clip],"numItems")},importFiles:function(){return true;},save:function(){return 0;},createNewSequenceFromClips:function(name,clips){sequence.name=name;return sequence;}};
 var app={version:"26.0",project:project,projects:{numProjects:1},isDocumentOpen:function(){return this.projects.numProjects>0;},isDocument:function(){return true;},newProject:function(p){this.project=project;this.project.path=p;this.projects.numProjects=1;return true;},openDocument:function(p){return this.newProject(p);}};
 `,c);
 vm.runInContext(fs.readFileSync(path.join(__dirname,"../cep/host.jsx"),"utf8"),c);
 return {context:c,run:(op,args={},deadline=Date.now()/1000+20)=>JSON.parse(vm.runInContext("$._bubblePremiere.dispatch("+JSON.stringify({operation:op,arguments:args,expires_at:deadline})+")",c)),evalScript:(code,cb)=>cb(vm.runInContext(code,c)),set:code=>vm.runInContext(code,c)};
}
module.exports={fixture};
