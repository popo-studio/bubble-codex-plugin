"""Opt-in PS 0.5 native workflow acceptance through installed Codex MCP only.

Uses owned documents; existing documents remain open and the active one is
restored. Script calls are readbacks only; all edits use structured tools.
"""
import argparse
from pathlib import Path
import uuid

from codex_plugin_smoke import AppServer, ROOT, plugin_read
from photoshop_document_acceptance import payload


def run(binary, catalog):
    server = AppServer(binary)
    thread = sid = original = None
    owned = set()
    label = 'BubbleWorkflow_' + uuid.uuid4().hex
    try:
        server.initialize()
        server.request('plugin/install', {'marketplacePath': str(catalog), 'pluginName': 'photoshop-control'}, timeout=120)
        detail = plugin_read(server, catalog, 'photoshop-control')
        assert detail['summary']['localVersion'] == '0.5.0', detail['summary']
        thread = server.request('thread/start', {'cwd': str(ROOT), 'ephemeral': True,
                                'sandbox': 'read-only', 'approvalPolicy': 'never'}, timeout=120)['thread']['id']
        rows = server.request('mcpServerStatus/list', {'threadId': thread, 'serverName': 'photoshop',
                              'detail': 'toolsAndAuthOnly'}, timeout=120)['data']
        row = next(r for r in rows if r['name'] == 'photoshop')
        assert not row.get('toolsError') and len(row['tools']) == 39, row

        def call(tool, **arguments):
            return payload(server.request('mcpServer/tool/call', {'threadId': thread, 'server': 'photoshop',
                           'tool': 'photoshop_' + tool, 'arguments': arguments}, timeout=120))

        sessions = call('list_sessions')
        sid = sessions['selection']['selected']
        assert sid, sessions
        original = call('scene_info', session_id=sid)['data']
        document = call('create_document', session_id=sid, width=512, height=512, name=label)['data']
        did = document['id']; owned.add(did)

        def op(tool, **arguments):
            call('activate_document', session_id=sid, document_id=did)
            return call(tool, session_id=sid, document_id=did, **arguments)['data']

        def read(code):
            return op('execute_script', code=code)

        def refusal(tool, expected, **arguments):
            try:
                op(tool, **arguments)
            except AssertionError as error:
                assert expected.lower() in str(error).lower(), str(error)
            else:
                raise AssertionError(tool + ' should refuse this operation')

        layer = op('create_layer', name='Pixels')['layer_id']
        op('selection', action='rectangle', left=128, top=128, right=384, bottom=384)
        op('fill_selection', layer_id=layer, color='#FF0000')
        saved = op('save_selection', name='Bubble quarter')
        assert saved['channel_name'] == 'Bubble quarter'
        refusal('save_selection', 'exists', name='Bubble quarter')
        op('selection', action='deselect')
        loaded = op('load_selection', name='Bubble quarter')
        assert loaded['bounds'] == [128, 128, 384, 384], loaded
        op('selection', action='rectangle', left=0, top=0, right=256, bottom=512)
        loaded = op('load_selection', name='Bubble quarter', mode='intersect')
        assert loaded['bounds'] == [128, 128, 256, 384], loaded
        op('selection', action='deselect')
        print('PASS native alpha selection save/load/intersection and overwrite refusal', flush=True)

        op('transform_layer', layer_id=layer, scale_x=50, scale_y=100, angle=90)
        bounds = read('var b=app.activeDocument.activeLayer.bounds;[b[0].as("px"),b[1].as("px"),b[2].as("px"),b[3].as("px")];')
        assert all(abs(a-b) <= 1 for a,b in zip(bounds, [128,192,384,320])), bounds
        op('set_blend_mode', layer_id=layer, mode='multiply')
        assert read('String(app.activeDocument.activeLayer.blendMode);').lower().endswith('multiply')
        group = op('create_layer', kind='group', name='Folder')['layer_id']
        op('move_layer', layer_id=layer, relative_layer_id=group, placement='inside')
        op('select_layer', layer_id=layer)
        assert read('app.activeDocument.activeLayer.parent.id;') == group
        upper = op('create_layer', name='Upper')['layer_id']
        op('move_layer', layer_id=upper, relative_layer_id=group, placement='before')
        assert read('app.activeDocument.layers[0].id;') == upper
        refusal('move_layer', 'descendant', layer_id=group, relative_layer_id=layer, placement='inside')
        print('PASS native layer geometry, blend mode, grouping/order and cycle refusal', flush=True)

        text = op('create_layer', kind='text', name='Caption', text='Bubble', font_size=24)['layer_id']
        font = read('app.activeDocument.activeLayer.textItem.font;')
        op('update_layer', layer_id=text, visible=False)
        op('set_text_style', layer_id=text, font=font, color='#336699', justification='center', tracking=120)
        style = read('var l=app.activeDocument.activeLayer;({font:l.textItem.font,color:l.textItem.color.rgb.hexValue,align:String(l.textItem.justification),tracking:l.textItem.tracking,visible:l.visible});')
        assert style['font'] == font and style['color'].upper() == '336699' and style['tracking'] == 120, style
        assert style['align'].lower().endswith('center') and style['visible'] is False, style
        refusal('set_text_style', 'not installed', layer_id=text, font='BubbleDefinitelyMissingFont-123', color='#FFFFFF')
        assert read('app.activeDocument.activeLayer.textItem.color.rgb.hexValue;').upper() == '336699'
        print('PASS native text style with hidden-layer preservation and missing-font preflight', flush=True)

        baseline = op('history_info')
        marker = op('create_layer', name='History marker')['layer_id']
        refusal('restore_history', 'History changed', index=baseline['active_index'], expected_history=baseline)
        current = op('history_info')
        op('restore_history', index=baseline['active_index'], expected_history=current)
        assert marker not in [l['layer_id'] for l in op('inspect_document')['layers']]
        print('PASS native history inspection, stale-state refusal and restore', flush=True)

        duplicate = op('duplicate_document', name=label + '_copy')
        copied = duplicate['id']; owned.add(copied)
        assert copied != did and duplicate['width'] == duplicate['height'] == 512, duplicate
        copy_info = call('inspect_document', session_id=sid, document_id=copied)['data']
        source_info = call('inspect_document', session_id=sid, document_id=did)['data']
        assert [l['name'] for l in copy_info['layers']] == [l['name'] for l in source_info['layers']]
        print('PASS native layered document duplication with independent document ID', flush=True)
    finally:
        try:
            if sid and original is not None:
                for document_id in list(owned):
                    call('activate_document', session_id=sid, document_id=document_id)
                    call('close_document', session_id=sid, document_id=document_id, discard_changes=True)
                    owned.remove(document_id)
                if original['active_document_id'] is not None:
                    call('activate_document', session_id=sid, document_id=original['active_document_id'])
                remaining = call('scene_info', session_id=sid)['data']
                assert sorted(d['id'] for d in remaining['documents']) == sorted(d['id'] for d in original['documents'])
                print('PASS owned test documents closed; original documents preserved', flush=True)
            if thread:
                server.request('thread/unsubscribe', {'threadId': thread})
        finally:
            server.close()
    print('PASS all nine new PS workflow tools through installed Codex plugin', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--codex', required=True)
    parser.add_argument('--catalog', type=Path, default=ROOT / '.agents/plugins/marketplace.json')
    args = parser.parse_args()
    run(args.codex, args.catalog)
