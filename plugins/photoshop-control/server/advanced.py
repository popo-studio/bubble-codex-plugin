"""Selection, raster-mask, pixel adjustments/filters and embedded smart objects."""
import json
from pathlib import Path
from operations import number, text

HELPERS=r'''function s(v){return stringIDToTypeID(v);}function c(v){return charIDToTypeID(v);}function layerDescriptor(id,documentId){var r=new ActionReference();r.putIdentifier(s("layer"),id);r.putIdentifier(s("document"),documentId===undefined?app.activeDocument.id:documentId);return executeActionGet(r);}function layerState(id,documentId){var a=layerDescriptor(id,documentId),has=a.hasKey(s("hasUserMask"))&&a.getBoolean(s("hasUserMask")),smart=a.hasKey(s("smartObject")),linked=null;if(smart){var o=a.getObjectValue(s("smartObject"));if(o.hasKey(s("linked")))linked=o.getBoolean(s("linked"));}return {has_user_mask:has,mask_enabled:has?(a.hasKey(s("userMaskEnabled"))?a.getBoolean(s("userMaskEnabled")):null):null,smart_object:smart,smart_object_linked:linked};}function selectionInfo(d){var b=null;try{var v=d.selection.bounds;b=[v[0].as("px"),v[1].as("px"),v[2].as("px"),v[3].as("px")];}catch(e){}return {document_id:d.id,has_selection:b!==null,bounds:b};}function singleLayer(d,l){var r=new ActionReference();r.putIdentifier(s("layer"),l.id);var a=new ActionDescriptor();a.putReference(s("null"),r);a.putBoolean(s("makeVisible"),false);executeAction(s("select"),a,DialogModes.NO);if(d.activeLayer.id!==l.id)throw new Error("Photoshop selected a different layer");}function pixels(d){if(d.mode!==DocumentMode.RGB&&d.mode!==DocumentMode.GRAYSCALE)throw new Error("Only RGB/grayscale component channels are supported");d.activeChannels=d.componentChannels;}function normalPixels(d,l){if(l.typename!=="ArtLayer"||l.kind!==LayerKind.NORMAL)throw new Error("Operation requires a normal pixel layer; no implicit rasterization");if(l.allLocked||l.pixelsLocked)throw new Error("Pixel layer is locked");if(d.bitsPerChannel!==BitsPerChannelType.EIGHT&&d.bitsPerChannel!==BitsPerChannelType.SIXTEEN)throw new Error("Only 8/16-bit pixel operations are supported");}'''

SHARED_SMART_GUARD = r'''function otherSmartObjects(documentId,layerId){var found=[];function walk(ls,d){for(var i=0;i<ls.length;i++){var l=ls[i];if(l.typename==="LayerSet")walk(l.layers,d);else if(l.typename==="ArtLayer"&&l.kind===LayerKind.SMARTOBJECT&&!(d.id===documentId&&l.id===layerId))found.push({document_id:d.id,document_name:d.name,layer_id:l.id,layer_name:l.name});}}for(var j=0;j<app.documents.length;j++)walk(app.documents[j].layers,app.documents[j]);return found;}'''
HELPERS += SHARED_SMART_GUARD

OPERATIONS={'selection_info' ,'selection','fill_selection','layer_mask','adjust_color','apply_filter','smart_object'}


def build(op,r):
    prefix='var d=app.activeDocument;'
    if op=='selection_info':return prefix+'return selectionInfo(d);'
    if op=='selection':
        action=r.get('action');mode=r.get('mode','replace')
        if mode not in ('replace','add','subtract','intersect'):raise ValueError('Unknown selection mode')
        if action in ('all','deselect','invert'):
            if mode!='replace':raise ValueError('mode is only applicable to rectangle')
            method={'all':'selectAll','deselect':'deselect','invert':'invert'}[action]
            return prefix+f'd.selection.{method}();return selectionInfo(d);'
        if action in ('expand','contract','feather'):
            if mode!='replace':raise ValueError('mode is only applicable to rectangle')
            amount=number(r.get('amount'),'amount',1,500,True)
            return prefix+'if(!selectionInfo(d).has_selection)throw new Error("No selection exists");'+f'd.selection.{action}({amount});return selectionInfo(d);'
        if action not in ('rectangle','ellipse'):raise ValueError('Unknown selection action')
        values=[number(r.get(k),k,0,30000) for k in ('left','top','right','bottom')]
        left,top,right,bottom=values
        if right<=left or bottom<=top:raise ValueError('Selection bounds must have positive area')
        guard=f'if({right}>d.width.as("px")||{bottom}>d.height.as("px"))throw new Error("Selection exceeds canvas bounds");'
        if action=='rectangle':
            kind={'replace':'REPLACE','add':'EXTEND','subtract':'DIMINISH','intersect':'INTERSECT'}[mode]
            points=','.join('[new UnitValue('+str(x)+',"px"),new UnitValue('+str(y)+',"px")]' for x,y in [(left,top),(right,top),(right,bottom),(left,bottom)])
            return prefix+guard+f'd.selection.select([{points}],SelectionType.{kind},0,false);return selectionInfo(d);'
        if mode!='replace':raise ValueError('Ellipse supports replace mode only')
        return prefix+guard+f'var a=new ActionDescriptor(),ref=new ActionReference();ref.putProperty(c("Chnl"),c("fsel"));a.putReference(c("null"),ref);var shape=new ActionDescriptor();shape.putUnitDouble(c("Top "),c("#Pxl"),{top});shape.putUnitDouble(c("Left"),c("#Pxl"),{left});shape.putUnitDouble(c("Btom"),c("#Pxl"),{bottom});shape.putUnitDouble(c("Rght"),c("#Pxl"),{right});a.putObject(c("T   "),c("Elps"),shape);executeAction(c("setd"),a,DialogModes.NO);return selectionInfo(d);'
    layer_id=number(r.get('layer_id'),'layer_id',0,2147483647,True)
    prefix+=f'var l=findLayer(d.layers,{layer_id});if(!l)throw new Error("Layer ID does not belong to selected document");'
    if op=='fill_selection':
        color=r.get('color')
        if not isinstance(color,str) or len(color)!=7 or color[0]!='#' or any(ch not in '0123456789abcdefABCDEF' for ch in color[1:]):raise ValueError('color must be #RRGGBB')
        opacity=number(r.get('opacity',100),'opacity',0,100)
        return prefix+'normalPixels(d,l);if(!selectionInfo(d).has_selection)throw new Error("An explicit selection is required; use selection all for the full image");singleLayer(d,l);pixels(d);var color=new SolidColor();color.rgb.hexValue='+json.dumps(color[1:])+f';d.selection.fill(color,ColorBlendMode.NORMAL,{opacity},false);return layerInfo(l);'
    if op=='layer_mask':
        action=r.get('action');mode=r.get('mode','reveal_all')
        if action not in ('create','enable','disable','delete','apply'):raise ValueError('Unknown raster mask action')
        state='var state=layerState(l.id);'
        if action=='create':
            modes={'reveal_all':'RvlA','hide_all':'HdAl','reveal_selection':'RvlS','hide_selection':'HdSl'}
            if mode not in modes:raise ValueError('Unknown mask creation mode')
            pre='if(state.has_user_mask)throw new Error("Layer already has a raster mask");'
            if 'selection' in mode:pre+='if(!selectionInfo(d).has_selection)throw new Error("Mask mode requires an existing selection");'
            code='var a=new ActionDescriptor();a.putClass(c("Nw  "),c("Chnl"));var ref=new ActionReference();ref.putEnumerated(c("Chnl"),c("Chnl"),c("Msk "));a.putReference(c("At  "),ref);a.putEnumerated(c("Usng"),c("UsrM"),c("'+modes[mode]+'"));executeAction(c("Mk  "),a,DialogModes.NO);'
        else:
            pre='if(!state.has_user_mask)throw new Error("Layer has no raster mask");'
            if action in ('enable','disable'):
                value='true' if action=='enable' else 'false'
                code='var a=new ActionDescriptor(),ref=new ActionReference();ref.putIdentifier(s("layer"),l.id);a.putReference(s("null"),ref);var value=new ActionDescriptor();value.putBoolean(s("userMaskEnabled"),'+value+');a.putObject(s("to"),s("layer"),value);executeAction(s("set"),a,DialogModes.NO);'
            else:
                if action=='apply':pre+='normalPixels(d,l);'
                code='var a=new ActionDescriptor(),ref=new ActionReference();ref.putEnumerated(c("Chnl"),c("Chnl"),c("Msk "));a.putReference(c("null"),ref);a.putBoolean(s("apply"),'+('true' if action=='apply' else 'false')+');executeAction(s("delete"),a,DialogModes.NO);'
        return prefix+state+pre+'singleLayer(d,l);pixels(d);try{'+code+'return layerInfo(d.activeLayer);}finally{pixels(d);}'
    if op=='adjust_color':
        action=r.get('adjustment')
        if action=='brightness_contrast':
            bright=number(r.get('brightness',0),'brightness',-100,100,True);contrast=number(r.get('contrast',0),'contrast',-100,100,True)
            code=f'l.adjustBrightnessContrast({bright},{contrast});'
        elif action=='levels':
            black=number(r.get('input_black',0),'input_black',0,253,True);white=number(r.get('input_white',255),'input_white',2,255,True);gamma=number(r.get('gamma',1),'gamma',0.1,9.99)
            outblack=number(r.get('output_black',0),'output_black',0,255,True);outwhite=number(r.get('output_white',255),'output_white',0,255,True)
            if black>=white or outblack>=outwhite:raise ValueError('Black level must be lower than white level')
            code=f'l.adjustLevels({black},{white},{gamma},{outblack},{outwhite});'
        elif action in ('invert','desaturate'):code='l.'+action+'();'
        else:raise ValueError('Unknown color adjustment')
        return prefix+'normalPixels(d,l);singleLayer(d,l);pixels(d);'+code+'return layerInfo(l);'
    if op=='apply_filter':
        action=r.get('filter')
        if action=='gaussian_blur':code='l.applyGaussianBlur('+str(number(r.get('radius',1),'radius',0.1,250))+');'
        elif action=='unsharp_mask':
            radius=number(r.get('radius',1),'radius',0.1,250);amount=number(r.get('amount',100),'amount',1,500);threshold=number(r.get('threshold',0),'threshold',0,255,True)
            code=f'l.applyUnSharpMask({amount},{radius},{threshold});'
        elif action=='median':
            radius=number(r.get('radius',1),'radius',1,100)
            if int(radius)!=radius:raise ValueError('Median radius must be a whole number of pixels')
            code='l.applyMedianNoise('+str(int(radius))+');'
        else:raise ValueError('Unknown filter')
        return prefix+'normalPixels(d,l);singleLayer(d,l);pixels(d);'+code+'return layerInfo(l);'
    if op=='smart_object':
        action=r.get('action')
        if action=='convert':
            return prefix+'normalPixels(d,l);singleLayer(d,l);pixels(d);executeAction(s("newPlacedLayer"),undefined,DialogModes.NO);return layerInfo(d.activeLayer);'
        if action!='replace_contents':raise ValueError('Only convert and replace_contents are supported')
        path=r.get('path')
        if not isinstance(path,str) or not Path(path).is_absolute():raise ValueError('Replacement path must be absolute')
        path=Path(path).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in {'.png','.jpg','.jpeg','.tif','.tiff','.bmp'}:raise ValueError('Replacement must be an existing PNG/JPEG/TIFF/BMP image; scripts, PDF, raw and linked assets are not accepted')
        return prefix+'var state=layerState(l.id);if(!state.smart_object||state.smart_object_linked!==false)throw new Error("Replacement requires a verified embedded smart object; linked/unknown objects are refused");var otherObjects=otherSmartObjects(d.id,l.id);if(otherObjects.length)throw new Error("Smart-object replacement refused: another smart object exists in an open document and shared embedded content cannot be ruled out. Other document/layer identities: "+encode(otherObjects));singleLayer(d,l);pixels(d);var file=new File('+json.dumps(str(path),ensure_ascii=True)+');if(!file.exists)throw new Error("Replacement image no longer exists");var a=new ActionDescriptor();a.putPath(c("null"),file);executeAction(s("placedLayerReplaceContents"),a,DialogModes.NO);return layerInfo(d.activeLayer);'
    raise ValueError('Unsupported operation')
