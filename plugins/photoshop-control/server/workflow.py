"""Document copies, layer arrangement/style, history and reusable selections."""
import json
import re
from operations import number,text,flag

OPERATIONS={'duplicate_document','transform_layer','move_layer','set_blend_mode','set_text_style','history_info','restore_history','save_selection','load_selection'}
HISTORY='function historyInfo(d){var a=[],active=-1;if(d.historyStates.length>1000)throw Error("History exceeds 1000 states");for(var i=0;i<d.historyStates.length;i++){a.push(d.historyStates[i].name);if(d.historyStates[i]===d.activeHistoryState)active=i;}return {document_id:d.id,names:a,active_index:active};}'

def build(op,r):
    prefix='var d=app.activeDocument;'
    if op=='duplicate_document':return prefix+'var copy=d.duplicate('+text(r.get('name','Copy'),'name')+','+flag(r.get('merged',False),'merged')+');return docInfo(copy);'
    if op=='history_info':return prefix+HISTORY+'return historyInfo(d);'
    if op=='restore_history':
        index=number(r.get('index'),'index',0,999,True);expected=r.get('expected_history')
        if not isinstance(expected,dict) or set(expected)!={'document_id','names','active_index'} or not isinstance(expected['names'],list) or len(expected['names'])>1000:raise ValueError('Use exact history_info result for expected_history')
        return prefix+HISTORY+'var expected='+json.dumps(expected,ensure_ascii=True,allow_nan=False)+';var current=historyInfo(d);if(encode(current)!==encode({document_id:expected.document_id,names:expected.names,active_index:expected.active_index}))throw Error("History changed; inspect before restoring");if('+str(index)+'>=d.historyStates.length)throw Error("History index missing");d.activeHistoryState=d.historyStates['+str(index)+'];return historyInfo(d);'
    if op in ('save_selection','load_selection'):
        name=text(r.get('name'),'name');setup=prefix+'var name='+name+';var matches=[];for(var i=0;i<d.channels.length;i++)if(d.channels[i].name===name)matches.push(d.channels[i]);'
        if op=='save_selection':return setup+'if(matches.length)throw Error("Channel name exists; choose a new name");if(!selectionInfo(d).has_selection)throw Error("No selection exists");var channel=d.channels.add();try{channel.name=name;d.selection.store(channel,SelectionType.REPLACE);}catch(e){channel.remove();throw e;}return {channel_name:channel.name};'
        mode={'replace':'REPLACE','add':'EXTEND','subtract':'DIMINISH','intersect':'INTERSECT'}.get(r.get('mode','replace'))
        if mode is None:raise ValueError('Unknown selection mode')
        return setup+'if(matches.length!==1||matches[0].kind===ChannelType.COMPONENT)throw Error("Choose a unique alpha channel");d.selection.load(matches[0],SelectionType.'+mode+');return selectionInfo(d);'
    lid=number(r.get('layer_id'),'layer_id',0,2147483647,True)
    prefix+=f'var l=findLayer(d.layers,{lid});if(!l)throw Error("Selected layer missing");if(l.allLocked)throw Error("Layer is locked");'
    if op=='transform_layer':
        x=number(r.get('scale_x',100),'scale_x',.01,10000);y=number(r.get('scale_y',100),'scale_y',.01,10000);angle=number(r.get('angle',0),'angle',-360,360)
        return prefix+'if(l.isBackgroundLayer||(l.linkedLayers&&l.linkedLayers.length))throw Error("Background or linked layers cannot be transformed implicitly");singleLayer(d,l);pixels(d);'+f'l.resize({x},{y},AnchorPosition.MIDDLECENTER);l.rotate({angle},AnchorPosition.MIDDLECENTER);return layerInfo(l);'
    if op=='move_layer':
        tid=number(r.get('relative_layer_id'),'relative_layer_id',0,2147483647,True);placement={'before':'PLACEBEFORE','after':'PLACEAFTER','inside':'INSIDE'}.get(r.get('placement','before'))
        if placement is None:raise ValueError('Unknown placement')
        return prefix+f'var target=findLayer(d.layers,{tid});if(!target||target===l||l.isBackgroundLayer)throw Error("Invalid layer move target");var parent=target;while(parent&&parent.typename!=="Document"){{if(parent===l)throw Error("Cannot move a group into its descendant");parent=parent.parent;}}'+('if(target.typename!=="LayerSet")throw Error("Inside target must be a group");' if placement=='INSIDE' else '')+f'l.move(target,ElementPlacement.{placement});return layerInfo(l);'
    if op=='set_blend_mode':
        mode=r.get('mode');allowed={'normal','multiply','screen','overlay','softlight','hardlight','difference','darken','lighten','color','luminosity'}
        if mode not in allowed:raise ValueError('Unsupported blend mode')
        return prefix+'l.blendMode=BlendMode.'+mode.upper()+';return {layer_id:l.id,blend_mode:String(l.blendMode)};'
    if op=='set_text_style':
        changes=[];preflight=''
        if r.get('font') is not None:
            font=text(r['font'],'font');preflight+='var wanted='+font+';var found=false;for(var i=0;i<app.fonts.length;i++)if(app.fonts[i].postScriptName===wanted)found=true;if(!found)throw Error("Exact PostScript font is not installed");';changes.append('l.textItem.font=wanted;')
        if r.get('color') is not None:
            color=r['color']
            if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):raise ValueError('Use #RRGGBB color')
            changes.append('var rgb=new SolidColor();rgb.rgb.hexValue='+json.dumps(color[1:])+';l.textItem.color=rgb;')
        if r.get('justification') is not None:
            value={'left':'LEFT','center':'CENTER','right':'RIGHT'}.get(r['justification'])
            if not value:raise ValueError('Invalid justification')
            changes.append('l.textItem.justification=Justification.'+value+';')
        if r.get('tracking') is not None:changes.append('l.textItem.tracking='+str(number(r['tracking'],'tracking',-1000,10000,True))+';')
        if not changes:raise ValueError('Specify at least one text style property')
        return prefix+'if(l.typename!=="ArtLayer"||l.kind!==LayerKind.TEXT)throw Error("Selected layer is not text");'+preflight+'var visible=l.visible;try{'+''.join(changes)+'}finally{l.visible=visible;}return layerInfo(l);'
    raise ValueError('Unknown workflow operation')
