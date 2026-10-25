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

        function requireName(value){if(typeof value!=="string"||!value.replace(/\s/g,"")||value.length>255||/[\x00-\x1f]/.test(value))fail("Name must be 1-255 characters");return value;}
        function finite(value,min,max){if(typeof value!=="number"||!isFinite(value)||value<min||value>max)fail("Numeric value outside allowed range");return value;}
        if(job.operation==="create_bin"){
            n=item(p,a.parent_item_id);if(n!==p.rootItem&&n.type!==2)fail("Parent must be a bin or project root");var name=requireName(a.name);if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");var bin=n.createBin(name);if(!bin)fail("Bin creation failed");return {item_id:text(bin.nodeId),name:text(bin.name)};
        }
        if(job.operation==="rename_item"){
            n=item(p,a.item_id);if(n===p.rootItem)fail("Project root cannot be renamed");n.name=requireName(a.name);return {item_id:text(n.nodeId),name:text(n.name)};
        }
        if(job.operation==="move_item"){
            n=item(p,a.item_id);var destination=item(p,a.parent_item_id);if(n===p.rootItem||n===destination||(destination!==p.rootItem&&destination.type!==2))fail("Choose an item and a different destination bin");
            var descendants=items(n);if(descendants.truncated)fail("Item subtree exceeds limit");for(i=0;i<descendants.rows.length;i++)if(text(descendants.rows[i].nodeId)===text(destination.nodeId))fail("Cannot move a bin into its descendant");
            if(typeof n.moveBin!=="function")fail("Host does not expose public moveBin");if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");n.moveBin(destination);var moved=destination.children,verified=false;if(!moved||moved.numItems>1000)fail("Destination children unavailable or exceed limit after move; inspect before retry");for(i=0;i<moved.numItems;i++)if(text(moved[i].nodeId)===a.item_id)verified=true;if(!verified)fail("Move outcome not verified; inspect before retry");return {item_id:text(n.nodeId),parent_item_id:text(destination.nodeId),name:text(n.name)};
        }
        if(/^(rename_sequence|duplicate_sequence|track_state|delete_marker|sequence_settings|set_playhead|set_sequence_range|sequence_markers|create_marker|update_marker)$/.test(job.operation)){
            if(p.sequences.numSequences>1000)fail("Sequence list exceeds limit");for(i=0;i<p.sequences.numSequences;i++)if(text(p.sequences[i].sequenceID)===a.sequence_id)s=p.sequences[i];if(!s)fail("Sequence ID not found");
            if(job.operation==="duplicate_sequence"){
                var copyName=requireName(a.name),before={};for(i=0;i<p.sequences.numSequences;i++){before[text(p.sequences[i].sequenceID)]=true;if(p.sequences[i].name===copyName)fail("Sequence name already exists");}if(p.sequences.numSequences>=1000)fail("Sequence count limit reached");if(typeof s.clone!=="function")fail("Host does not expose public sequence clone");if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");var cloned=s.clone(),copies=[];for(i=0;i<p.sequences.numSequences;i++)if(!before.hasOwnProperty(text(p.sequences[i].sequenceID)))copies.push(p.sequences[i]);if(cloned!==true||copies.length!==1)fail("Clone outcome unknown; inspect sequences before retry");copies[0].name=copyName;return seq(copies[0]);
            }
            if(job.operation==="track_state"){
                if(a.kind!=="video"&&a.kind!=="audio")fail("Track kind must be video or audio");var tracks=a.kind==="video"?s.videoTracks:s.audioTracks;finite(a.index,0,999);if(a.index%1||a.index>=tracks.numTracks)fail("Track index missing");var chosen=tracks[a.index];if(typeof chosen.isMuted!=="function"||chosen.id===undefined)fail("Host track identity/mute API unavailable");
                function trackInfo(){return {id:text(chosen.id),name:text(chosen.name),kind:a.kind,index:a.index,muted:!!chosen.isMuted()};}var current=trackInfo();if(a.muted!==null){if(typeof a.muted!=="boolean")fail("Boolean muted required");var expected=a.expected_state;if(!expected||expected.id!==current.id||expected.name!==current.name||expected.kind!==current.kind||expected.index!==current.index||expected.muted!==current.muted)fail("Track state changed; read track_state again");if(typeof chosen.setMute!=="function")fail("Host track mute API unavailable");if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");chosen.setMute(a.muted?1:0);current=trackInfo();if(current.muted!==a.muted)fail("Mute outcome not verified; inspect before retry");}return current;
            }
            if(job.operation==="rename_sequence"){s.name=requireName(a.name);return seq(s);}
            if(job.operation==="sequence_settings"){var settings=s.getSettings();return {sequence:seq(s),video_width:settings.videoFrameWidth,video_height:settings.videoFrameHeight,pixel_aspect:settings.videoPixelAspectRatio,video_display_format:settings.videoDisplayFormat,audio_display_format:settings.audioDisplayFormat,frame_rate_ticks:settings.videoFrameRate?text(settings.videoFrameRate.ticks):null,playhead_ticks:text(s.getPlayerPosition().ticks),in_seconds:s.getInPointAsTime().seconds,out_seconds:s.getOutPointAsTime().seconds};}
            if(job.operation==="set_playhead"){if(typeof a.ticks!=="string"||!/^\d{1,18}$/.test(a.ticks))fail("Use a nonnegative integer tick string up to 18 digits");s.setPlayerPosition(a.ticks);return {playhead_ticks:text(s.getPlayerPosition().ticks)};}
            if(job.operation==="set_sequence_range"){finite(a.start,0,864000);finite(a.end,0,864000);if(a.end<=a.start)fail("End must exceed start");s.setInPoint(a.start);s.setOutPoint(a.end);return {in_seconds:s.getInPointAsTime().seconds,out_seconds:s.getOutPointAsTime().seconds};}
            var markers=s.markers;if(markers.numMarkers>1000)fail("Marker count exceeds limit");var marker,found=null,markerRows=[];
            function markerInfo(m){return {guid:text(m.guid),name:text(m.name),comments:text(m.comments),start:m.start.seconds,end:m.end.seconds};}
            for(marker=markers.getFirstMarker();marker;marker=markers.getNextMarker(marker)){markerRows.push(markerInfo(marker));if(text(marker.guid)===a.guid)found=marker;if(markerRows.length>1000)fail("Marker traversal exceeds limit");}
            if(job.operation==="sequence_markers")return {markers:markerRows};
            if(job.operation==="delete_marker"){
                if(!found)fail("Marker GUID not found");var expected=a.expected_marker,current=markerInfo(found);if(!expected||expected.guid!==current.guid||expected.name!==current.name||expected.comments!==current.comments||expected.start!==current.start||expected.end!==current.end)fail("Marker changed; read sequence_markers again");if(typeof markers.deleteMarker!=="function")fail("Host marker delete API unavailable");if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");markers.deleteMarker(found);for(marker=markers.getFirstMarker(),i=0;marker;marker=markers.getNextMarker(marker)){if(++i>1000)fail("Marker traversal exceeds limit");if(text(marker.guid)===a.guid)fail("Marker deletion not verified; inspect before retry");}return {deleted_guid:a.guid};
            }
            if(typeof a.name!=="string"||a.name.length>255||typeof a.comments!=="string"||a.comments.length>10000)fail("Marker text exceeds limits");
            if(job.operation==="create_marker"){finite(a.start,0,864000);finite(a.duration,0,864000);if(a.start+a.duration>864000)fail("Marker range exceeds limit");if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");marker=markers.createMarker(a.start);marker.name=a.name;marker.comments=a.comments;marker.end=a.start+a.duration;return markerInfo(marker);}
            if(!found)fail("Marker GUID not found");if(a.end!==null){finite(a.end,0,864000);if(a.end<found.start.seconds)fail("Marker end precedes start");}if(a.color!==null){finite(a.color,0,7);if(a.color%1)fail("Color must be an integer");}
            if(new Date().getTime()>=job.expires_at*1000)fail("Request expired");found.name=a.name;found.comments=a.comments;if(a.end!==null)found.end=a.end;if(a.color!==null)found.setColorByIndex(a.color);return markerInfo(found);
        }
        fail("Unsupported operation");
    }
    return {dispatch:function(job){try{return json({ok:true,data:execute(job)});}catch(e){return json({ok:false,error:{code:"host",message:text(e.message||e),note:"Partial changes may exist; never retry automatically."}});}}};
})();
