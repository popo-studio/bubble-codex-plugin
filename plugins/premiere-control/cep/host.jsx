// Bubble Premiere: public ExtendScript DOM only. No QE or arbitrary script operation.
$._bubblePremiere = (function () {
    function text(v) { return String(v == null ? "" : v); }
    function quote(s) { return '"' + text(s).replace(/[\\"\x00-\x1f\u2028\u2029]/g, function(c) {var n=c.charCodeAt(0).toString(16);return "\\u"+ ("0000"+n).slice(-4);}) + '"'; }
    function json(v) {
        if(v===null || v===undefined)return "null";
        if(typeof v==="string")return quote(v);
        if(typeof v==="number")return isFinite(v)?String(v):"null";
        if(typeof v==="boolean")return String(v);
        var parts=[], i;
        if(v instanceof Array){for(i=0;i<v.length;i++)parts.push(json(v[i]));return "["+parts.join(",")+"]";}
        for(i in v)if(v.hasOwnProperty(i))parts.push(quote(i)+":"+json(v[i]));
        return "{"+parts.join(",")+"}";
    }
    function fail(message){throw new Error(message);}
    function checkVersion(){if(parseInt(app.version,10)!==26 || !/^\d+\./.test(app.version))fail("Premiere 26.x required; older hosts are not supported");}
    function target(p){return {id:text(p.documentID),name:text(p.name),path:text(p.path)};}
    function seq(s){return {id:text(s.sequenceID),name:text(s.name),width:s.frameSizeHorizontal,height:s.frameSizeVertical,timebase:text(s.timebase)};}
    function items(root) {
        var out=[], stack=[root], n, i, dropped=false;
        while(stack.length && out.length<1000){n=stack.pop();out.push(n);if(n.children)for(i=n.children.numItems-1;i>=0;i--){if(stack.length+out.length>=1001){dropped=true;break;}stack.push(n.children[i]);}}
        return {rows:out,truncated:dropped||stack.length>0};
    }
    function item(p,id){var scan=items(p.rootItem), i, found=null;for(i=0;i<scan.rows.length;i++)if(text(scan.rows[i].nodeId)===id)found=scan.rows[i];if(scan.truncated)fail("Project item scan truncated; narrow project before changing media");if(!found)fail("Item ID not found");return found;}
    function path(value){if(typeof value!=="string" || !/^(?:[A-Za-z]:[\\\/]|\\\\[^\\]+\\[^\\]+)/.test(value) || /[\x00\r\n]/.test(value))fail("An absolute Windows file path is required");var f=new File(value);if(!f.exists)fail("File does not exist: "+value);if(/\.(jsx?|jsxbin|exe|bat|cmd|ps1|prproj|aep)$/i.test(value))fail("Only media files, not scripts or projects, are accepted here");return f.fsName;}
    function execute(job){
        checkVersion();
        if(job.operation==="host_info"){var current=app.project;return {app:"premiere",version:app.version,targets:current&&current.documentID?[target(current)]:[]};}
        if(typeof job.expires_at!=="number" || !isFinite(job.expires_at) || new Date().getTime()>=job.expires_at*1000)fail("Request expired before execution");
        var a=job.arguments || {}, p=app.project, i, rows=[], s, n;
        if(job.operation==="new_project" || job.operation==="open_project"){
            if(!app.projects || app.projects.numProjects!==0 || app.isDocumentOpen())fail("Close existing projects yourself before creating or opening a project; no save/discard is implicit");
            if(typeof a.path!=="string" || !/^[A-Za-z]:[\\\/]/.test(a.path) || /[\x00\r\n]/.test(a.path) || !/\.prproj$/i.test(a.path))fail("Choose an absolute local .prproj path");
            var projectFile=new File(a.path);
            if(!projectFile.parent.exists)fail("Destination parent folder must exist");
            if(job.operation==="new_project"){
                if(projectFile.exists)fail("Refusing to overwrite an existing project");
                if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");
                if(!app.newProject(projectFile.fsName))fail("Project creation failed; inspect before retry");
            }else{
                if(!projectFile.exists || !app.isDocument(projectFile.fsName))fail("Not an existing Premiere project");
                if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");
                if(!app.openDocument(projectFile.fsName,false,false,false,false))fail("Project open failed; inspect before retry");
            }
            if(!app.project || !app.project.documentID)fail("No project became available; inspect Premiere");
            return {project:target(app.project)};
        }
        if(!p || !a.project_id || text(p.documentID)!==a.project_id)fail("Selected project is no longer active; no fallback");
        if(job.operation==="project_info"){
            for(i=0;i<Math.min(p.sequences.numSequences,1000);i++)rows.push(seq(p.sequences[i]));
            return {project:target(p),sequences:rows,truncated:p.sequences.numSequences>1000};
        }
        if(job.operation==="inspect_media"){
            var scan=items(p.rootItem);
            for(i=0;i<scan.rows.length;i++){n=scan.rows[i];var r={id:text(n.nodeId),name:text(n.name),type:n.type};try{r.path=n.getMediaPath();r.offline=n.isOffline();}catch(e){r.unverified=text(e);}rows.push(r);}
            return {items:rows,truncated:scan.truncated};
        }
        if(job.operation==="import_files"){
            if(!(a.paths instanceof Array)||!a.paths.length||a.paths.length>100)fail("Choose 1-100 media paths");
            for(i=0;i<a.paths.length;i++)rows.push(path(a.paths[i]));
            if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");
            if(!p.importFiles(rows,true,p.rootItem,false))fail("Import failed; partial changes may exist");return {imported:true};
        }
        if(job.operation==="relink_media"){
            n=item(p,a.item_id);var media=path(a.path);if(!n.canChangeMediaPath())fail("Selected item cannot be relinked");
            if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");
            var changed=n.changeMediaPath(media,false);if(changed!==0)fail("Relink failed; inspect state before retry");return {relinked:true,item_id:a.item_id,path:n.getMediaPath()};
        }
        if(job.operation==="save_project"){
            if(!p.path)fail("Project has no existing path; save it in Premiere first");
            if(p.save()!==0)fail("Project save failed");return {saved:true,path:p.path};
        }
        if(job.operation==="create_sequence_from_clips"){
            if(typeof a.name!=="string"||!a.name.replace(/\s/g,"")||a.name.length>128)fail("Provide a sequence name of 1-128 characters");
            if(!(a.item_ids instanceof Array)||!a.item_ids.length||a.item_ids.length>100)fail("Choose 1-100 clip IDs");
            for(i=0;i<a.item_ids.length;i++){n=item(p,a.item_ids[i]);if(n.type===2 || n.isSequence() || n.isOffline())fail("Select online source clips, not bins or sequences");rows.push(n);}
            if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");
            s=p.createNewSequenceFromClips(a.name,rows,p.rootItem);if(!s)fail("Sequence creation failed; inspect before retry");return {created:true,sequence:seq(s)};
        }
        if(job.operation==="inspect_timeline"){
            for(i=0;i<p.sequences.numSequences;i++)if(text(p.sequences[i].sequenceID)===a.sequence_id)s=p.sequences[i];
            if(!s)fail("Sequence ID not found");
            var groups=[{kind:"video",tracks:s.videoTracks},{kind:"audio",tracks:s.audioTracks}], g,t,c,count=0,truncated=false;
            for(g=0;g<groups.length;g++)for(t=0;t<groups[g].tracks.numTracks;t++){
                var track=groups[g].tracks[t];for(c=0;c<track.clips.numItems;c++){
                    if(count>=1000){truncated=true;break;}n=track.clips[c];rows.push({kind:groups[g].kind,track:t,id:text(n.nodeId),name:text(n.name),item_id:n.projectItem?text(n.projectItem.nodeId):null,start_ticks:text(n.start.ticks),end_ticks:text(n.end.ticks),in_ticks:text(n.inPoint.ticks),out_ticks:text(n.outPoint.ticks)});count++;
                }
            }return {sequence:seq(s),clips:rows,truncated:truncated};
        }
        fail("Unsupported operation");
    }
    return {dispatch:function(job){try{return json({ok:true,data:execute(job)});}catch(e){return json({ok:false,error:{code:"host",message:text(e.message||e),note:"Partial changes may exist; never retry automatically."}});}}};
})();
