import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import workflow

@unittest.skipUnless(shutil.which('node'),'Node required for DOM behavioral tests')
class WorkflowTests(unittest.TestCase):
 def run_host(self,op,args,setup=''):
  base='''var events=[],l={id:2,name:'Layer',allLocked:false,isBackgroundLayer:false,linkedLayers:[],typename:'ArtLayer',kind:'text',visible:false,resize:function(x,y){events.push(['resize',x,y]);},rotate:function(a){events.push(['rotate',a]);},move:function(t,p){events.push(['move',t.id,p]);},textItem:{font:'Old'}};var d={id:1,layers:[l],channels:[],historyStates:[{name:'Open'},{name:'Paint'}],duplicate:function(n,m){events.push(['duplicate',n,m]);return {id:9};}};d.activeHistoryState=d.historyStates[1];l.parent=d;d.typename='Document';var app={activeDocument:d,fonts:[{postScriptName:'ExactFont'}]};var LayerKind={TEXT:'text'},AnchorPosition={MIDDLECENTER:0},ElementPlacement={PLACEBEFORE:1,PLACEAFTER:2,INSIDE:3},BlendMode={MULTIPLY:1},ChannelType={COMPONENT:0},Justification={CENTER:1};function findLayer(ls,id){return ls.find(x=>x.id===id)||null;}function layerInfo(x){return {id:x.id,font:x.textItem&&x.textItem.font,visible:x.visible};}function docInfo(x){return {id:x.id};}function singleLayer(){}function pixels(){}function selectionInfo(){return {has_selection:true};}function encode(v){return JSON.stringify(v);}'''
  body=workflow.build(op,args)
  code=base+setup+';var result;try{result={ok:true,data:(function(){'+body+'})()};}catch(e){result={ok:false,error:String(e)};}process.stdout.write(JSON.stringify({result,events,font:l.textItem.font,visible:l.visible}));'
  return json.loads(subprocess.run(['node','-e',code],capture_output=True,text=True,check=True).stdout)
 def test_transform_executes_requested_scale_and_angle(self):self.assertEqual(self.run_host('transform_layer',dict(layer_id=2,scale_x=50,scale_y=75,angle=90))['events'],[['resize',50,75],['rotate',90]])
 def test_linked_transform_refused_before_changes(self):self.assertEqual(self.run_host('transform_layer',dict(layer_id=2),'l.linkedLayers=[{}]')['events'],[])
 def test_group_cycle_refused(self):
  r=self.run_host('move_layer',dict(layer_id=2,relative_layer_id=3,placement='inside'),"var child={id:3,parent:l,typename:'LayerSet'};d.layers.push(child)");self.assertFalse(r['result']['ok']);self.assertEqual(r['events'],[])
 def test_missing_font_does_not_mutate(self):
  r=self.run_host('set_text_style',dict(layer_id=2,font='Missing'));self.assertFalse(r['result']['ok']);self.assertEqual(r['font'],'Old')
 def test_font_and_visibility_preserved(self):
  r=self.run_host('set_text_style',dict(layer_id=2,font='ExactFont',tracking=40));self.assertTrue(r['result']['ok']);self.assertEqual(r['font'],'ExactFont');self.assertFalse(r['visible'])
 def test_history_changed_rejected(self):self.assertFalse(self.run_host('restore_history',dict(index=0,expected_history={'document_id':1,'names':['Open'],'active_index':0}))['result']['ok'])
 def test_history_exact_snapshot_restores(self):self.assertEqual(self.run_host('restore_history',dict(index=0,expected_history={'document_id':1,'names':['Open','Paint'],'active_index':1}))['result']['data']['active_index'],0)
 def test_duplicate_is_new_document(self):self.assertEqual(self.run_host('duplicate_document',dict(name='Copy',merged=True))['result']['data']['id'],9)
 def test_existing_alpha_not_overwritten(self):self.assertFalse(self.run_host('save_selection',dict(name='Mask'),"d.channels=[{name:'Mask'}]")['result']['ok'])
 def test_invalid_color_rejected_before_script(self):
  with self.assertRaises(ValueError):workflow.build('set_text_style',dict(layer_id=2,color='red'))
 def test_explicit_unlock_and_relock(self):
  self.assertFalse(self.run_host('layer_lock',dict(layer_id=2,locked=False),'l.allLocked=true')['result']['data']['locked'])
  self.assertTrue(self.run_host('layer_lock',dict(layer_id=2,locked=True))['result']['data']['locked'])
 def test_unlock_never_changes_locked_parent_or_background(self):
  for setup in ['l.isBackgroundLayer=true','l.parent={typename:"LayerSet",allLocked:true,parent:d}']:
   self.assertFalse(self.run_host('layer_lock',dict(layer_id=2,locked=False),setup)['result']['ok'])
 def test_clipping_requires_lower_sibling_and_can_release(self):
  self.assertFalse(self.run_host('clipping_mask',dict(layer_id=2,enabled=True))['result']['ok'])
  self.assertTrue(self.run_host('clipping_mask',dict(layer_id=2,enabled=True),'d.layers.push({id:3})')['result']['data']['clipped'])
  self.assertFalse(self.run_host('clipping_mask',dict(layer_id=2,enabled=False),'l.grouped=true')['result']['data']['clipped'])
 def test_alpha_channel_rename_delete_and_protected_components(self):
  setup="ChannelType.MASKEDAREA=1;ChannelType.SELECTEDAREA=2;d.channels=[{name:'Mask',kind:1,remove:function(){events.push('delete-alpha');}}]"
  self.assertEqual(self.run_host('channels',dict(action='rename',name='Mask',new_name='Saved'),setup)['result']['data']['name'],'Saved')
  self.assertEqual(self.run_host('channels',dict(action='delete',name='Mask'),setup)['events'],['delete-alpha'])
  for kind in (0,3):
   r=self.run_host('channels',dict(action='delete',name='Mask'),setup+f';d.channels[0].kind={kind}')
   self.assertFalse(r['result']['ok']);self.assertEqual(r['events'],[])
 def test_channels_list_and_ambiguous_name_refused(self):
  setup="ChannelType.MASKEDAREA=1;ChannelType.SELECTEDAREA=2;d.channels=[{name:'RGB',kind:0},{name:'Mask',kind:1},{name:'Mask',kind:2}]"
  self.assertEqual([r['alpha'] for r in self.run_host('channels',dict(action='list'),setup)['result']['data']['channels']],[False,True,True])
  self.assertFalse(self.run_host('channels',dict(action='delete',name='Mask'),setup)['result']['ok'])

if __name__=='__main__':unittest.main()
