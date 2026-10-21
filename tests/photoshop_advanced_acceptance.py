"""Opt-in PS 0.4 native selection/mask/color/filter/smart-object acceptance."""
import argparse
from pathlib import Path
import uuid
from codex_plugin_smoke import AppServer, ROOT, plugin_read
from photoshop_document_acceptance import payload


def run(binary, catalog):
    s = AppServer(binary)
    thread = None
    sid = None
    original = None
    owned = set()
    folder = ROOT / '.test-runtime' / ('PSAdvanced_' + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    try:
        s.initialize()
        s.request('plugin/install', {'marketplacePath':str(catalog),'pluginName':'photoshop-control'}, timeout=120)
        detail = plugin_read(s,catalog,'photoshop-control')
        assert detail['summary']['localVersion']=='0.4.0', detail['summary']
        thread = s.request('thread/start',{'cwd':str(ROOT),'ephemeral':True,'sandbox':'read-only','approvalPolicy':'never'}, timeout=120)['thread']['id']
        status = s.request('mcpServerStatus/list',{'threadId':thread,'serverName':'photoshop','detail':'toolsAndAuthOnly'},timeout=120)
        row = next(r for r in status['data'] if r['name']=='photoshop')
        assert not row.get('toolsError') and len(row['tools'])==30 and row['pluginId']==detail['summary']['id'], row
        def call(tool, **args):
            return payload(s.request('mcpServer/tool/call',{'threadId':thread,'server':'photoshop','tool':'photoshop_'+tool,'arguments':args},timeout=120))
        sessions = call('list_sessions')
        sid = sessions['selection']['selected']
        assert sid, sessions
        original = call('scene_info',session_id=sid)['data']
        doc = call('create_document',session_id=sid,width=128,height=128,name=folder.name)['data']
        did = doc['id']; owned.add(did)
        def op(tool, **args):
            call('activate_document',session_id=sid,document_id=did)
            return call(tool,session_id=sid,document_id=did,**args)['data']
        def sample(x,y):
            code = '(function(){var cs=app.activeDocument.colorSamplers.add([new UnitValue('+str(x)+',"px"),new UnitValue('+str(y)+',"px")]);try{var c=cs.color.rgb;return [c.red,c.green,c.blue];}finally{cs.remove();}})();'
            return op('execute_script',code=code)
        def near(actual, expected, tolerance=3):
            assert len(actual)==len(expected)==3,(actual,expected)
            assert all(abs(a-b)<=tolerance for a,b in zip(actual,expected)), (actual,expected)
        layer = op('create_layer',name='Pixels')['layer_id']
        op('selection',action='all')
        op('fill_selection',layer_id=layer,color='#FF0000')
        op('selection',action='rectangle',left=0,top=0,right=64,bottom=128)
        selection = op('selection_info')
        assert selection['has_selection'] is True and selection['bounds']==[0,0,64,128], selection
        added=op('selection',action='rectangle',mode='add',left=64,top=0,right=128,bottom=128)
        assert added['bounds']==[0,0,128,128],added
        subtracted=op('selection',action='rectangle',mode='subtract',left=0,top=0,right=64,bottom=128)
        assert subtracted['bounds']==[64,0,128,128],subtracted
        intersected=op('selection',action='rectangle',mode='intersect',left=96,top=0,right=128,bottom=128)
        assert intersected['bounds']==[96,0,128,128],intersected
        op('selection',action='rectangle',left=0,top=0,right=64,bottom=128)
        op('fill_selection',layer_id=layer,color='#0000FF')
        op('selection',action='deselect')
        near(sample(20,64),[0,0,255]); near(sample(100,64),[255,0,0])
        op('selection',action='rectangle',left=32,top=32,right=96,bottom=96)
        expanded=op('selection',action='expand',amount=2)
        assert expanded['bounds']==[30,30,98,98],expanded
        contracted=op('selection',action='contract',amount=2)
        assert contracted['bounds']==[32,32,96,96],contracted
        assert op('selection',action='feather',amount=1)['has_selection'] is True
        assert op('selection',action='invert')['has_selection'] is True
        ellipse=op('selection',action='ellipse',left=32,top=32,right=96,bottom=96)
        assert ellipse['has_selection'] and all(abs(a-b)<=1 for a,b in zip(ellipse['bounds'],[32,32,96,96])),ellipse
        op('selection',action='deselect')
        print('PASS native selections and RGB fills, verified by pixel samples',flush=True)
        op('apply_filter',layer_id=layer,filter='gaussian_blur',radius=4)
        boundary = sample(62,64)
        assert boundary[0]>0 and boundary[2]>0, boundary
        op('apply_filter',layer_id=layer,filter='unsharp_mask',amount=50,radius=1,threshold=0)
        op('apply_filter',layer_id=layer,filter='median',radius=1)
        op('adjust_color',layer_id=layer,adjustment='invert')
        near(sample(20,64),[255,255,0])
        op('adjust_color',layer_id=layer,adjustment='desaturate')
        gray = sample(20,64)
        assert max(gray)-min(gray)<3, gray
        op('adjust_color',layer_id=layer,adjustment='levels',gamma=1.2)
        before = sample(20,64)
        op('adjust_color',layer_id=layer,adjustment='brightness_contrast',brightness=15,contrast=0)
        assert sample(20,64)[0]>before[0]
        print('PASS native blur/sharpen/median and color adjustments; pixels changed',flush=True)
        source = sample(100,64)
        op('selection',action='rectangle',left=0,top=0,right=64,bottom=128)
        mask = op('layer_mask',layer_id=layer,action='create',mode='reveal_selection')
        assert mask['has_user_mask'] is True and mask['mask_enabled'] is True, mask
        op('selection',action='deselect')
        near(sample(100,64),[255,255,255])
        left_before=sample(20,64)
        op('execute_script',code='var r=new ActionReference();r.putEnumerated(charIDToTypeID("Chnl"),charIDToTypeID("Chnl"),charIDToTypeID("Msk "));var q=new ActionDescriptor();q.putReference(charIDToTypeID("null"),r);q.putBoolean(charIDToTypeID("MkVs"),false);executeAction(charIDToTypeID("slct"),q,DialogModes.NO);true;')
        op('adjust_color',layer_id=layer,adjustment='invert')
        near(sample(20,64),[255-v for v in left_before])
        near(sample(100,64),[255,255,255])
        op('adjust_color',layer_id=layer,adjustment='invert')
        mask = op('layer_mask',layer_id=layer,action='disable')
        assert mask['mask_enabled'] is False
        near(sample(100,64),source)
        op('layer_mask',layer_id=layer,action='enable')
        near(sample(100,64),[255,255,255])
        op('layer_mask',layer_id=layer,action='delete')
        near(sample(100,64),source)
        op('layer_mask',layer_id=layer,action='create',mode='hide_all')
        near(sample(20,64),[255,255,255])
        op('layer_mask',layer_id=layer,action='delete')
        op('selection',action='rectangle',left=0,top=0,right=64,bottom=128)
        op('layer_mask',layer_id=layer,action='create',mode='hide_selection')
        op('selection',action='deselect')
        near(sample(20,64),[255,255,255]);near(sample(100,64),source)
        op('layer_mask',layer_id=layer,action='delete')
        op('layer_mask',layer_id=layer,action='create',mode='reveal_all')
        applied = op('layer_mask',layer_id=layer,action='apply')
        assert applied['has_user_mask'] is False, applied
        near(sample(100,64),source)
        print('PASS native mask creation/disable/enable/delete/apply and pixel effect',flush=True)
        op('layer_mask',layer_id=layer,action='create',mode='reveal_all')
        replacement = call('create_document',session_id=sid,width=128,height=128,name=folder.name+'_replacement')['data']
        rid = replacement['id']; owned.add(rid)
        inactive=call('inspect_document',session_id=sid,document_id=did)['data']
        inactive_layer=next(l for l in inactive['layers'] if l['layer_id']==layer)
        assert inactive_layer['has_user_mask'] is True,inactive_layer
        assert call('scene_info',session_id=sid)['data']['active_document_id']==rid
        pixel = call('create_layer',session_id=sid,document_id=rid,name='Replacement')['data']['layer_id']
        call('selection',session_id=sid,document_id=rid,action='all')
        call('fill_selection',session_id=sid,document_id=rid,layer_id=pixel,color='#00FF00')
        call('selection',session_id=sid,document_id=rid,action='deselect')
        path = folder / 'replacement.png'
        call('export_document',session_id=sid,document_id=rid,path=str(path))
        call('close_document',session_id=sid,document_id=rid,discard_changes=True); owned.remove(rid)
        op('layer_mask',layer_id=layer,action='delete')
        sentinel=op('create_layer',name='Do not convert')['layer_id']
        op('select_layer',layer_id=layer)
        op('execute_script',code='var r=new ActionReference();r.putIdentifier(stringIDToTypeID("layer"),'+str(sentinel)+');var a=new ActionDescriptor();a.putReference(stringIDToTypeID("null"),r);a.putEnumerated(stringIDToTypeID("selectionModifier"),stringIDToTypeID("selectionModifierType"),stringIDToTypeID("addToSelection"));a.putBoolean(stringIDToTypeID("makeVisible"),false);executeAction(stringIDToTypeID("select"),a,DialogModes.NO);true;')
        smart = op('smart_object',layer_id=layer,action='convert')
        print('SMART '+str(smart),flush=True)
        layer = smart['layer_id']
        assert smart['smart_object'] is True, smart
        inspected=op('inspect_document')
        untouched=next(l for l in inspected['layers'] if l['layer_id']==sentinel)
        assert untouched['smart_object'] is False,untouched
        twin=op('duplicate_layer',layer_id=layer,name='Shared smart comparison')['layer_id']
        op('update_layer',layer_id=twin,visible=False)
        try:
            op('smart_object',layer_id=layer,action='replace_contents',path=str(path))
        except AssertionError as error:
            assert 'Smart-object replacement refused: another smart object exists' in str(error),str(error)
            assert str(twin) in str(error),str(error)
        else:
            raise AssertionError('Shared smart replacement must be refused')
        near(sample(100,64),source)
        op('update_layer',layer_id=layer,visible=False)
        op('update_layer',layer_id=twin,visible=True)
        near(sample(100,64),source)
        op('delete_layer',layer_id=twin)
        op('update_layer',layer_id=layer,visible=True)
        replaced = op('smart_object',layer_id=layer,action='replace_contents',path=str(path))
        assert replaced['smart_object'] is True, replaced
        near(sample(64,64),[0,255,0])
        print('PASS native embedded smart-object conversion and replacement pixel verification',flush=True)
    finally:
        try:
            if sid and original is not None:
                for docid in list(owned):
                    call('activate_document',session_id=sid,document_id=docid)
                    call('close_document',session_id=sid,document_id=docid,discard_changes=True)
                    owned.remove(docid)
                if original['active_document_id'] is not None:
                    call('activate_document',session_id=sid,document_id=original['active_document_id'])
                after=call('scene_info',session_id=sid)['data']
                assert sorted(d['id'] for d in after['documents'])==sorted(d['id'] for d in original['documents'])
                print('PASS original user documents preserved and active document restored',flush=True)
            if thread:s.request('thread/unsubscribe',{'threadId':thread})
        finally:s.close()
    print('PASS all five feature groups through real installed Codex plugin',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',required=True)
    parser.add_argument('--codex',required=True)
    parser.add_argument('--catalog',type=Path,default=ROOT/'.agents/plugins/marketplace.json')
    args=parser.parse_args();run(args.codex,args.catalog)
