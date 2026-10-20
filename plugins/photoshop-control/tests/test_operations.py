"""Standard operation refusal rules and worker snapshot regression tests."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import main
import operations
import worker

class OperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime=Path(__file__).resolve().parents[1]/'.test-runtime'
        cls.runtime.mkdir(exist_ok=True)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=self.runtime)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_active_doc_guard_all_standard_mutations(self):
        requests=[('save_document',{'path':str(self.root/'a.psd')}),('export_document',{'path':str(self.root/'a.png')}),('close_document',{}),('resize_image',{'width':5,'height':5}),('resize_canvas',{'width':5,'height':5}),('crop_document',{'left':0,'top':0,'right':5,'bottom':5}),('rotate_document',{'angle':90}),('create_layer',{}),('update_layer',{'layer_id':0,'visible':False}),('duplicate_layer',{'layer_id':0}),('delete_layer',{'layer_id':0}),('translate_layer',{'layer_id':0,'x':1,'y':2}),('select_layer',{'layer_id':0})]
        for op,args in requests:
            with self.subTest(op=op):
                source=worker.source({'operation':op,'document_id':123,**args})
                self.assertIn('app.activeDocument.id!==123',source)
                self.assertIn('new Date().getTime()>',source)
    def test_output_existing_requires_authorized_overwrite(self):
        path=self.root/'existing.psd';path.touch()
        with self.assertRaises(ValueError):operations.build('save_document',{'path':str(path)})
        code=operations.build('save_document',{'path':str(path),'overwrite':True})
        self.assertIn('d.saveAs(f,options,false',code)
    def test_output_rejects_bad_path_extension_parent(self):
        for path in ['relative.psd',str(self.root/'bad.png'),str(self.root/'absent'/'a.psd')]:
            with self.assertRaises(ValueError):operations.build('save_document',{'path':path})
    def test_overwrite_requires_bool(self):
        with self.assertRaises(ValueError):operations.build('save_document',{'path':str(self.root/'a.psd'),'overwrite':1})
    def test_output_guard_repeated_at_write(self):
        code=operations.build('save_document',{'path':str(self.root/'a.psd')})
        self.assertEqual(code.count('Output exists; refusing overwrite'),2)
    def test_jpeg_flatten_only_copy_and_restore(self):
        code=operations.build('export_document',{'path':str(self.root/'a.jpg'),'format':'jpeg'})
        self.assertIn('copy.flatten()',code);self.assertNotIn('d.flatten()',code)
        self.assertIn('finally{try{if(copy)copy.close',code)
        self.assertIn('finally{app.activeDocument=d;}',code)
    def test_png_does_not_flatten(self):
        self.assertNotIn('flatten',operations.build('export_document',{'path':str(self.root/'a.png')}))
    def test_export_extension_quality(self):
        for args in [{'format':'jpeg','quality':13},{'format':'png','quality':True},{'format':'webp'}]:
            with self.assertRaises(ValueError):operations.build('export_document',{'path':str(self.root/'a.png'),**args})
    def test_dirty_close_refusal_default(self):
        self.assertIn('if(!d.saved&&!false)',operations.build('close_document',{}))
        self.assertIn('if(!d.saved&&!true)',operations.build('close_document',{'discard_changes':True}))
    def test_resize_units_and_ranges(self):
        self.assertIn('new UnitValue(20,"px")',operations.build('resize_image',{'width':20,'height':20}))
        for value in [True,0,1.5,30001]:
            with self.assertRaises(ValueError):operations.build('resize_image',{'width':value,'height':20})
        with self.assertRaises(ValueError):operations.build('resize_canvas',{'width':20000,'height':20000})
    def test_invalid_canvas_anchor(self):
        with self.assertRaises(ValueError):operations.build('resize_canvas',{'width':1,'height':1,'anchor':'unknown'})
    def test_crop_reversed_and_native_bound_check(self):
        with self.assertRaises(ValueError):operations.build('crop_document',{'left':5,'top':0,'right':4,'bottom':10})
        self.assertIn('Crop exceeds current document bounds',operations.build('crop_document',{'left':0,'top':0,'right':4,'bottom':10}))
    def test_rotate_finite(self):
        for value in [True,float('nan'),float('inf'),361]:
            with self.assertRaises(ValueError):operations.build('rotate_document',{'angle':value})
    def test_layer_identity_zero_valid_negative_invalid(self):
        self.assertIn('findLayer(d.layers,0)',operations.build('select_layer',{'layer_id':0}))
        for value in [-1,True,1.5]:
            with self.assertRaises(ValueError):operations.build('select_layer',{'layer_id':value})
    def test_layer_membership_checked(self):
        self.assertIn('Layer ID does not belong',operations.build('delete_layer',{'layer_id':8}))
    def test_create_text_units(self):
        code=operations.build('create_layer',{'kind':'text','text':'Hello','font_size':24})
        self.assertIn('new UnitValue(24,"pt")',code)
        self.assertIn('l.kind=LayerKind.TEXT',code)
    def test_update_text_type_guard_precedes_mutation(self):
        code=operations.build('update_layer',{'layer_id':8,'name':'New','text':'Hello'})
        self.assertLess(code.index('Selected layer is not a text layer'),code.index('l.name='))
    def test_text_changes_precede_final_layer_properties(self):
        code=operations.build('update_layer',{'layer_id':8,'text':'Hello','font_size':24,'name':'New','opacity':65,'visible':False})
        self.assertLess(code.index('l.textItem.contents='),code.index('l.name='))
        self.assertLess(code.index('l.textItem.size='),code.index('l.opacity='))
        self.assertLess(code.index('l.opacity='),code.index('l.visible=false'))
        self.assertLess(code.index('l.name='),code.index('l.visible=false'))
    def test_text_only_preserves_previous_visibility(self):
        for args in [{'text':'New'},{'font_size':24}]:
            code=operations.build('update_layer',{'layer_id':8,**args})
            self.assertLess(code.index('var previousVisible=l.visible'),code.index('l.textItem.'))
            self.assertIn('l.visible=previousVisible;',code)
        explicit=operations.build('update_layer',{'layer_id':8,'text':'New','visible':True})
        self.assertNotIn('l.visible=previousVisible;',explicit)
        self.assertIn('l.visible=true;',explicit)
    def test_update_requires_property(self):
        with self.assertRaises(ValueError):operations.build('update_layer',{'layer_id':8})
    def test_opacity_range_and_bool(self):
        for value in [-1,101,True,float('nan')]:
            with self.assertRaises(ValueError):operations.build('update_layer',{'layer_id':8,'opacity':value})
    def test_translate_units(self):
        self.assertIn('new UnitValue(-5,"px")',operations.build('translate_layer',{'layer_id':8,'x':-5,'y':2}))
    def test_inspect_contains_ids_and_text(self):
        code=worker.source({'operation':'inspect_document','document_id':2})
        self.assertIn('active_layer_id=d.activeLayer.id',code)
        self.assertIn('layer_id:l.id',code)
        self.assertIn('o.text=l.textItem.contents',code)
    def test_snapshot_independent_of_package(self):
        snapshot=Path(main._worker_path)
        self.assertNotEqual(snapshot.parent,Path(worker.__file__).parent)
        self.assertEqual({p.name for p in snapshot.parent.glob('*.py')},{'native.py','worker.py','operations.py'})
        for name in ['native.py','worker.py','operations.py']:
            self.assertEqual((snapshot.parent/name).read_bytes(),Path(worker.__file__).with_name(name).read_bytes())

if __name__=='__main__':unittest.main()
