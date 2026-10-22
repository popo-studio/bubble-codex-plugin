"""Opt-in native PS 0.5 color balance and filter pixel verification."""
import argparse
import uuid
from codex_plugin_smoke import AppServer, ROOT
from photoshop_document_acceptance import payload


def run(binary):
    server = AppServer(binary)
    thread = sid = did = original = None
    try:
        server.initialize()
        server.request('plugin/install', {'marketplacePath': str(ROOT / '.agents/plugins/marketplace.json'),
                        'pluginName': 'photoshop-control'}, timeout=120)
        thread = server.request('thread/start', {'cwd': str(ROOT), 'ephemeral': True,
                                 'sandbox': 'read-only', 'approvalPolicy': 'never'}, timeout=120)['thread']['id']
        server.request('mcpServerStatus/list', {'threadId': thread, 'serverName': 'photoshop',
                       'detail': 'toolsAndAuthOnly'}, timeout=120)

        def call(tool, **args):
            return payload(server.request('mcpServer/tool/call', {'threadId': thread, 'server': 'photoshop',
                           'tool': 'photoshop_' + tool, 'arguments': args}, timeout=120))

        sid = call('list_sessions')['selection']['selected']
        assert sid
        original = call('scene_info', session_id=sid)['data']
        did = call('create_document', session_id=sid, width=128, height=128,
                   name='BubbleFilters_' + uuid.uuid4().hex)['data']['id']

        def op(tool, **args):
            return call(tool, session_id=sid, document_id=did, **args)['data']

        def samples():
            return op('execute_script', code='(function(){var a=[];for(var x=50;x<=78;x+=2){var s=app.activeDocument.colorSamplers.add([new UnitValue(x,"px"),new UnitValue(64,"px")]);try{var c=s.color.rgb;a.push([c.red,c.green,c.blue]);}finally{s.remove();}}return a;})();')

        layer = op('create_layer', name='Filter pixels')['layer_id']
        op('selection', action='all')
        op('fill_selection', layer_id=layer, color='#808080')
        op('selection', action='deselect')
        op('adjust_color', layer_id=layer, adjustment='color_balance', midtones=[60,0,0])
        balanced = samples()[0]
        assert balanced[0] > balanced[1] + 10 and balanced[0] > balanced[2] + 10, balanced
        print('PASS native color balance RGB pixel result', flush=True)
        op('selection', action='all')
        op('fill_selection', layer_id=layer, color='#000000')
        op('selection', action='rectangle', left=64, top=0, right=128, bottom=128)
        op('fill_selection', layer_id=layer, color='#FFFFFF')
        op('selection', action='deselect')
        before = samples()
        op('apply_filter', layer_id=layer, filter='motion_blur', radius=20, angle=0)
        blurred = samples()
        assert blurred != before and any(10 < p[0] < 245 for p in blurred), blurred
        print('PASS native motion blur alters edge pixels', flush=True)
        op('apply_filter', layer_id=layer, filter='add_noise', amount=20, distribution='gaussian', monochromatic=True)
        noisy = samples()
        assert noisy != blurred and all(max(p)-min(p)<3 for p in noisy), noisy
        print('PASS native monochromatic Gaussian noise pixel result', flush=True)
        # A linear motion-blurred ramp can be invariant under sharpening.
        # Noise supplies actual local high-frequency content to sharpen.
        op('apply_filter', layer_id=layer, filter='sharpen')
        sharp = samples()
        assert sharp != noisy, (sharp, noisy)
        print('PASS native sharpen alters textured pixels', flush=True)
    finally:
        try:
            if did is not None:
                call('activate_document', session_id=sid, document_id=did)
                call('close_document', session_id=sid, document_id=did, discard_changes=True)
            if original is not None:
                if original['active_document_id'] is not None:
                    call('activate_document', session_id=sid, document_id=original['active_document_id'])
                after = call('scene_info', session_id=sid)['data']
                assert [d['id'] for d in after['documents']] == [d['id'] for d in original['documents']]
                print('PASS original documents preserved', flush=True)
            if thread:
                server.request('thread/unsubscribe', {'threadId': thread})
        finally:
            server.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--codex', required=True)
    args = parser.parse_args()
    run(args.codex)
