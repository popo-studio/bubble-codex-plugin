"""Validated standard document and layer operations compiled to ExtendScript."""
import json
import math
from pathlib import Path


def number(value, label, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum or (integer and not isinstance(value, int)):
        raise ValueError(f"{label} must be {'an integer' if integer else 'a finite number'} in [{minimum}, {maximum}]")
    return value


def text(value, label, limit=255, allow_empty=False):
    if not isinstance(value, str) or (not value and not allow_empty) or len(value)>limit or ('\x00' in value):
        raise ValueError(f"{label} must be a string of at most {limit} characters")
    return json.dumps(value,ensure_ascii=True)


def flag(value, label):
    if not isinstance(value,bool): raise ValueError(label+" must be boolean")
    return 'true' if value else 'false'


def output_file(request, extensions):
    raw=request.get('path')
    if not isinstance(raw,str) or not Path(raw).is_absolute(): raise ValueError('Output path must be absolute')
    path=Path(raw).resolve()
    if path.suffix.lower() not in extensions or not path.parent.is_dir() or path.is_dir(): raise ValueError('Output extension must match the requested format and parent directory must exist')
    overwrite=request.get('overwrite',False)
    flag(overwrite,'overwrite')
    if path.exists() and not overwrite: raise ValueError('Output already exists; overwrite authorization is required')
    setup='var f=new File('+json.dumps(str(path),ensure_ascii=True)+');'
    guard='if(!f.parent.exists)throw new Error("Output directory no longer exists");if(f.exists&&!'+flag(overwrite,'overwrite')+')throw new Error("Output exists; refusing overwrite");'
    return setup,guard


LAYER_HELPERS=r'''function layerInfo(l){var o={layer_id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,typename:l.typename,locked:l.allLocked};if(l.typename==="ArtLayer"){o.kind=String(l.kind);o.clipped=l.grouped;if(l.kind===LayerKind.TEXT){o.text=l.textItem.contents;o.font_size=Number(l.textItem.size.as("pt"));o.font=l.textItem.font;}}var owner=l.parent;while(owner&&owner.typename!=="Document")owner=owner.parent;if(!owner)throw new Error("Cannot identify layer owner document");var state=layerState(l.id,owner.id);o.has_user_mask=state.has_user_mask;o.mask_enabled=state.mask_enabled;o.smart_object=state.smart_object;o.smart_object_linked=state.smart_object_linked;return o;}function findLayer(ls,id){for(var i=0;i<ls.length;i++){var l=ls[i];if(l.id===id)return l;if(l.typename==="LayerSet"){var found=findLayer(l.layers,id);if(found)return found;}}return null;}'''


def build(op,r):
    prefix='var d=app.activeDocument;'
    if op=='save_document':
        setup,guard=output_file(r,{'.psd'})
        return prefix+setup+guard+'var options=new PhotoshopSaveOptions();options.layers=true;'+guard+'d.saveAs(f,options,false,Extension.LOWERCASE);return docInfo(d);'
    if op=='export_document':
        fmt=r.get('format','png')
        if fmt not in ('png','jpeg'):raise ValueError('format must be png or jpeg')
        setup,guard=output_file(r,{'.png'} if fmt=='png' else {'.jpg','.jpeg'})
        quality=number(r.get('quality',10),'quality',0,12,True)
        export='var options=new PNGSaveOptions();' if fmt=='png' else 'copy.flatten();var options=new JPEGSaveOptions();options.quality='+str(quality)+';'
        return prefix+setup+guard+'var copy=null;try{copy=d.duplicate("Bubble export copy",false);if(copy.mode!==DocumentMode.RGB)copy.changeMode(ChangeMode.RGB);copy.bitsPerChannel=BitsPerChannelType.EIGHT;'+export+guard+'copy.saveAs(f,options,true,Extension.LOWERCASE);return {path:f.fsName,format:'+json.dumps(fmt)+',source_document_id:d.id};}finally{try{if(copy)copy.close(SaveOptions.DONOTSAVECHANGES);}finally{app.activeDocument=d;}}'
    if op=='close_document':
        discard=flag(r.get('discard_changes',False),'discard_changes')
        return prefix+'if(!d.saved&&!'+discard+')throw new Error("Document has unsaved changes; explicit discard_changes authorization required");var id=d.id;d.close(SaveOptions.DONOTSAVECHANGES);return {closed_document_id:id};'
    if op in ('resize_image','resize_canvas'):
        w=number(r.get('width'),'width',1,30000,True);h=number(r.get('height'),'height',1,30000,True)
        if w*h>100000000:raise ValueError('Dimensions exceed 100 million pixels')
        if op=='resize_image':
            resolution=r.get('resolution')
            resolution='undefined' if resolution is None else str(number(resolution,'resolution',1,1200))
            return prefix+f'd.resizeImage(new UnitValue({w},"px"),new UnitValue({h},"px"),{resolution},ResampleMethod.BICUBIC);return docInfo(d);'
        anchor=r.get('anchor','center')
        anchors={'center':'MIDDLECENTER','top_left':'TOPLEFT','top':'TOPCENTER','top_right':'TOPRIGHT','left':'MIDDLELEFT','right':'MIDDLERIGHT','bottom_left':'BOTTOMLEFT','bottom':'BOTTOMCENTER','bottom_right':'BOTTOMRIGHT'}
        if anchor not in anchors:raise ValueError('Unsupported canvas anchor')
        return prefix+f'd.resizeCanvas(new UnitValue({w},"px"),new UnitValue({h},"px"),AnchorPosition.{anchors[anchor]});return docInfo(d);'
    if op=='crop_document':
        values=[number(r.get(k),k,0,30000) for k in ['left','top','right','bottom']]
        left,top,right,bottom=values
        if right<=left or bottom<=top:raise ValueError('Crop must have positive width and height')
        bounds=','.join(f'new UnitValue({v},"px")' for v in values)
        return prefix+f'if({right}>d.width.as("px")||{bottom}>d.height.as("px"))throw new Error("Crop exceeds current document bounds");d.crop([{bounds}]);return docInfo(d);'
    if op=='rotate_document':
        angle=number(r.get('angle'),'angle',-360,360)
        return prefix+f'd.rotateCanvas({angle});return docInfo(d);'
    if op=='create_layer':
        kind=r.get('kind','pixel');name=text(r.get('name','Layer'),'name')
        if kind not in ('pixel','group','text'):raise ValueError('kind must be pixel, group or text')
        setup='var l=d.layerSets.add();' if kind=='group' else 'var l=d.artLayers.add();'
        if kind=='text':
            contents=text(r.get('text','Text'),'text',100000,True);size=number(r.get('font_size',48),'font_size',1,1296)
            setup+=f'l.kind=LayerKind.TEXT;l.textItem.contents={contents};l.textItem.size=new UnitValue({size},"pt");'
        return prefix+setup+f'l.name={name};return layerInfo(l);'
    layer_id=number(r.get('layer_id'),'layer_id',0,2147483647,True)
    prefix+=f'var l=findLayer(d.layers,{layer_id});if(!l)throw new Error("Layer ID does not belong to the selected document");'
    if op=='update_layer':
        changes=[]
        if r.get('name') is not None:changes.append('l.name='+text(r['name'],'name')+';')
        if r.get('opacity') is not None:changes.append('l.opacity='+str(number(r['opacity'],'opacity',0,100))+';')
        text_changes=[]
        if r.get('text') is not None:text_changes.append('l.textItem.contents='+text(r['text'],'text',100000,True)+';')
        if r.get('font_size') is not None:text_changes.append('l.textItem.size=new UnitValue('+str(number(r['font_size'],'font_size',1,1296))+',"pt");')
        if text_changes:
            changes=['if(l.typename!=="ArtLayer"||l.kind!==LayerKind.TEXT)throw new Error("Selected layer is not a text layer");var previousVisible=l.visible;']+text_changes+changes
        # Photoshop may reveal a text layer when contents/font size change.
        # Apply requested visibility last so the final state matches the request.
        if r.get('visible') is not None:changes.append('l.visible='+flag(r['visible'],'visible')+';')
        elif text_changes:changes.append('l.visible=previousVisible;')
        if not changes:raise ValueError('At least one layer property must be supplied')
        return prefix+''.join(changes)+'return layerInfo(l);'
    if op=='duplicate_layer':
        rename='' if r.get('name') is None else 'copy.name='+text(r['name'],'name')+';'
        return prefix+'var copy=l.duplicate();'+rename+'return layerInfo(copy);'
    if op=='delete_layer':return prefix+'var id=l.id;l.remove();return {deleted_layer_id:id};'
    if op=='translate_layer':
        x=number(r.get('x'),'x',-30000,30000);y=number(r.get('y'),'y',-30000,30000)
        return prefix+f'l.translate(new UnitValue({x},"px"),new UnitValue({y},"px"));return layerInfo(l);'
    if op=='select_layer':return prefix+'d.activeLayer=l;return layerInfo(l);'
    raise ValueError('Unsupported operation')
