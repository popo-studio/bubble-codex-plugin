"""Parameter validation and target isolation for advanced Photoshop operations."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import advanced
import worker

class AdvancedTests(unittest.TestCase):
    def test_selection_modes(self):
        for mode,constant in [('replace','REPLACE'),('add','EXTEND'),('subtract','DIMINISH'),('intersect','INTERSECT')]:
            code=advanced.build('selection',dict(action='rectangle',mode=mode,left=1,top=2,right=10,bottom=12))
            self.assertIn('SelectionType.'+constant,code)
            self.assertIn('Selection exceeds canvas',code)
    def test_invalid_bounds(self):
        for values in [dict(left=True,top=0,right=10,bottom=10),dict(left=10,top=0,right=1,bottom=10),dict(left=0,top=float('nan'),right=10,bottom=10)]:
            with self.assertRaises(ValueError):advanced.build('selection',dict(action='rectangle',**values))
    def test_ellipse_only_replace(self):
        with self.assertRaises(ValueError):advanced.build('selection',dict(action='ellipse',mode='add',left=0,top=0,right=10,bottom=10))
        self.assertIn('Elps',advanced.build('selection',dict(action='ellipse',left=0,top=0,right=10,bottom=10)))
    def test_selection_amount(self):
        for value in [True,0,501,2.5,float('inf')]:
            with self.assertRaises(ValueError):advanced.build('selection',dict(action='feather',amount=value))
        self.assertIn('No selection exists',advanced.build('selection',dict(action='expand',amount=2)))
    def test_read_selection_no_mutation(self):
        code=advanced.build('selection_info',{})
        self.assertEqual(code,'var d=app.activeDocument;return selectionInfo(d);')
    def test_fill_color_and_opacity(self):
        for color in ['red','#123','#12345g','123456']:
            with self.assertRaises(ValueError):advanced.build('fill_selection',dict(layer_id=1,color=color))
        with self.assertRaises(ValueError):advanced.build('fill_selection',dict(layer_id=1,color='#123456',opacity=101))
    def test_fill_requires_selection_and_pixels(self):
        code=advanced.build('fill_selection',dict(layer_id=1,color='#123456'))
        self.assertIn('An explicit selection is required',code)
        self.assertIn('normalPixels(d,l)',code)
        self.assertIn('singleLayer(d,l);pixels(d)',code)
    def test_mask_creation_modes(self):
        for mode in ['reveal_all','hide_all','reveal_selection','hide_selection']:
            code=advanced.build('layer_mask',dict(layer_id=1,action='create',mode=mode))
            self.assertIn('Layer already has a raster mask',code)
            self.assertIn('finally{pixels(d);}',code)
            if 'selection' in mode:self.assertIn('Mask mode requires an existing selection',code)
    def test_mask_apply_only_normal_pixels(self):
        self.assertIn('normalPixels(d,l)',advanced.build('layer_mask',dict(layer_id=1,action='apply')))
        self.assertNotIn('normalPixels(d,l)',advanced.build('layer_mask',dict(layer_id=1,action='delete')))
    def test_mask_missing_guard(self):
        for action in ['enable','disable','delete','apply']:
            self.assertIn('Layer has no raster mask',advanced.build('layer_mask',dict(layer_id=1,action=action)))
    def test_unknown_actions(self):
        for op,field in [('selection','action'),('layer_mask','action'),('adjust_color','adjustment'),('apply_filter','filter'),('smart_object','action')]:
            with self.assertRaises(ValueError):advanced.build(op,dict(layer_id=1,**{field:'unknown'}))
    def test_levels_validation(self):
        for args in [dict(input_black=100,input_white=50),dict(gamma=0),dict(output_black=255,output_white=0),dict(input_black=True)]:
            with self.assertRaises(ValueError):advanced.build('adjust_color',dict(layer_id=1,adjustment='levels',**args))
    def test_adjustments_explicit_single_pixel_target(self):
        for adjustment in ['brightness_contrast','levels','invert','desaturate']:
            code=advanced.build('adjust_color',dict(layer_id=1,adjustment=adjustment))
            self.assertIn('normalPixels(d,l);singleLayer(d,l);pixels(d);',code)
    def test_blur_bounds(self):
        for value in [0,251,True,float('nan')]:
            with self.assertRaises(ValueError):advanced.build('apply_filter',dict(layer_id=1,filter='gaussian_blur',radius=value))
    def test_median_integral_float(self):
        self.assertIn('applyMedianNoise(2)',advanced.build('apply_filter',dict(layer_id=1,filter='median',radius=2.0)))
        with self.assertRaises(ValueError):advanced.build('apply_filter',dict(layer_id=1,filter='median',radius=2.5))
    def test_unsharp_bounds(self):
        with self.assertRaises(ValueError):advanced.build('apply_filter',dict(layer_id=1,filter='unsharp_mask',amount=501))
    def test_smart_conversion_returns_new_identity(self):
        code=advanced.build('smart_object',dict(layer_id=1,action='convert'))
        self.assertIn('singleLayer(d,l)',code)
        self.assertIn('return layerInfo(d.activeLayer)',code)
    def test_smart_replacement_only_known_embedded(self):
        root=Path(__file__).resolve().parents[1]/'.test-runtime';root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            image=Path(directory)/'image.png';image.touch()
            code=advanced.build('smart_object',dict(layer_id=1,action='replace_contents',path=str(image)))
            self.assertIn('state.smart_object_linked!==false',code)
            self.assertIn('otherSmartObjects(d.id,l.id)',code)
            self.assertLess(code.index('if(otherObjects.length)'),code.index('singleLayer(d,l)'))
            self.assertLess(code.index('if(otherObjects.length)'),code.index('placedLayerReplaceContents'))
            self.assertIn('encode(otherObjects)',code)
            self.assertIn('Replacement image no longer exists',code)
            for extension in ['.jsx','.psjs','.pdf','.psd']:
                bad=Path(directory)/('bad'+extension);bad.touch()
                with self.assertRaises(ValueError):advanced.build('smart_object',dict(layer_id=1,action='replace_contents',path=str(bad)))
    def test_inactive_layer_inspection_binds_owner_document(self):
        code=worker.source({'operation':'inspect_document','document_id':77})
        self.assertIn('var owner=l.parent;while(owner&&owner.typename!=="Document")owner=owner.parent',code)
        self.assertIn('layerState(l.id,owner.id)',code)
        self.assertIn('putIdentifier(s("document"),documentId===undefined?app.activeDocument.id:documentId)',code)
        self.assertNotIn('app.activeDocument=d;',code)
    def test_shared_smart_guard_scans_all_documents_and_nested_groups(self):
        self.assertIn('j<app.documents.length',advanced.SHARED_SMART_GUARD)
        self.assertIn('walk(l.layers,d)',advanced.SHARED_SMART_GUARD)
        self.assertIn('d.id===documentId&&l.id===layerId',advanced.SHARED_SMART_GUARD)
        self.assertIn('document_id:d.id',advanced.SHARED_SMART_GUARD)
        self.assertIn('layer_id:l.id',advanced.SHARED_SMART_GUARD)
    def test_multiselect_modifier_not_used(self):
        self.assertNotIn('selectionModifier',advanced.HELPERS)
        self.assertIn('putIdentifier(s("layer"),l.id)',advanced.HELPERS)
        self.assertIn('d.activeChannels=d.componentChannels',advanced.HELPERS)
    def test_common_document_and_expiration_guard(self):
        for op,args in [('selection_info',{}),('selection',dict(action='all')),('fill_selection',dict(layer_id=0,color='#123456')),('layer_mask',dict(layer_id=0,action='create')),('adjust_color',dict(layer_id=0,adjustment='invert')),('apply_filter',dict(layer_id=0,filter='gaussian_blur')),('smart_object',dict(layer_id=0,action='convert'))]:
            code=worker.source(dict(operation=op,document_id=99,**args))
            self.assertIn('app.activeDocument.id!==99',code)
            self.assertIn('new Date().getTime()>',code)
            with self.assertRaises(ValueError):worker.source(dict(operation=op,document_id=99,expires_at=1,**args))

if __name__=='__main__':unittest.main()
