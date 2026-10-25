"""Exercise the production C# TCP/queue code with minimal Unity API test doubles.

No Unity Editor license is needed. This does not replace real Editor validation.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import client


def main():
    data = Path(os.environ.get("UNITY_EDITOR_DATA", "C:/Program Files/Unity/Hub/Editor/6000.1.0f1/Editor/Data"))
    scratch_root = ROOT / ".test-runtime"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unity-protocol-", dir=scratch_root) as directory:
        scratch = Path(directory)
        (scratch / "Assets").mkdir()
        exe = scratch / "Harness.exe"
        mono = str(data / "MonoBleedingEdge/bin/mono.exe")
        compiler = str(data / "MonoBleedingEdge/lib/mono/4.5/csc.exe")
        subprocess.run([mono, compiler, "/nologo", "/target:exe", "/reference:System.Web.Extensions.dll", "/out:" + str(exe), str(ROOT / "unity/Editor/BubbleUnityBridge.cs"), str(ROOT / "tests/UnityStubs.cs")], check=True, timeout=60)
        os.environ["BUBBLE_UNITY_SESSION_DIR"] = str(scratch / "sessions")
        env = {**os.environ, "BUBBLE_UNITY_TEST_PROJECT": str(scratch)}
        processes = []
        try:
            for _ in range(2):
                processes.append(subprocess.Popen([mono, str(exe)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            deadline = time.monotonic() + 15
            while len(client.sessions()) != 2 and time.monotonic() < deadline:
                time.sleep(.05)
            sessions = client.sessions()
            assert len(sessions) == 2, "Two C# bridges failed to start"
            first, second = sessions
            assert first["port"] != second["port"] and first["token"] != second["token"]
            assert client.request("status")["error"]["code"] == "session_selection"
            pid = first["pid"]

            def call(method, payload=None, timeout=3):
                return client.request("invoke_method", {"type_name": "BubbleHarness", "method_name": method, "with_payload": payload is not None, "payload": payload}, pid=pid, timeout=timeout)

            assert client.request("status", pid=pid)["ok"]
            objects=client.request('list_objects',{'limit':100},pid=pid)
            assert objects['ok'],objects
            scene_token=objects['data']['scene_token']
            preview_id=int(call('PreviewObject')['data']['result'])
            rejected=client.request('object_action',dict(action='rename',expected_scene=scene_token,object_id=preview_id,name='Forbidden'),pid=pid)
            assert not rejected['ok'] and 'preview' in rejected['error']['message'].lower(),rejected
            def edit(action, **args):
                return client.request('object_action',dict(action=action,expected_scene=scene_token,**args),pid=pid)
            created=edit('create',kind='cube',name='Fixture cube')
            assert created['ok'],created
            object_id=created['data']['objects'][0]['id']
            changed=edit('transform',object_id=object_id,position=[1,2,3],scale=[2,2,2])
            assert changed['ok'] and changed['data']['objects'][0]['position']==[1,2,3],changed
            rotated=edit('transform',object_id=object_id,rotation=[10,20,30])
            assert rotated['ok'] and rotated['data']['objects'][0]['rotation']==[10,20,30],rotated
            parent=edit('create',kind='empty',name='Parent')['data']['objects'][0]['id']
            attached=edit('parent',object_id=object_id,parent_id=parent)
            assert attached['ok'] and attached['data']['objects'][0]['parent_id']==parent,attached
            assert attached['data']['objects'][0]['position']==[1,2,3]
            assert not edit('parent',object_id=parent,parent_id=object_id)['ok']
            assert not edit('parent',object_id=object_id,parent_id=preview_id)['ok']
            assert not edit('active',object_id=object_id)['ok']
            inactive=edit('active',object_id=parent,active=False,has_active=True)
            assert inactive['ok'] and not inactive['data']['objects'][0]['active'],inactive
            child=client.request('inspect_object',dict(object_id=object_id,expected_scene=scene_token),pid=pid)['data']['objects'][0]
            assert child['active'] and not child['active_in_hierarchy'],child
            detached=edit('parent',object_id=object_id,parent_id=0)
            assert detached['ok'] and detached['data']['objects'][0]['parent_id']==0 and detached['data']['objects'][0]['active_in_hierarchy'],detached
            assert not client.request('scene_action',dict(action='new',expected_scene=scene_token),pid=pid)['ok'], 'Dirty scene was discarded'
            assert edit('rename',object_id=object_id,name='Renamed')['ok']
            assert edit('duplicate',object_id=object_id)['ok']
            assert edit('delete',object_id=object_id)['ok']
            assert not edit('rename',object_id=object_id,name='Stale')['ok']
            assert client.request('list_objects',{'limit':100},pid=second['pid'])['data']['objects']==[], 'Other instance changed'
            assert not client.request('object_action',dict(action='create',kind='cube',expected_scene='old'),pid=pid)['ok']
            saved=client.request('scene_action',dict(action='save',expected_scene=scene_token,path='Assets/fixture.unity'),pid=pid)
            assert saved['ok'],saved
            scene_token=saved['data']['scene_token']
            assert not client.request('scene_action',dict(action='save',expected_scene=scene_token,path='Assets/fixture.unity'),pid=pid)['ok']
            reset=client.request('scene_action',dict(action='new',expected_scene=scene_token),pid=pid)
            assert reset['ok'],reset
            assert not edit('create',kind='cube')['ok'], 'Old scene token survived new scene'
            print('PASS structured Unity create/transform/rename/duplicate/delete, scene dirty/overwrite/identity guards and instance isolation (stub DOM)')
            assert call("Echo", "Unicode 你好")["data"]["result"] == "Unicode 你好"
            assert call("Throw")["error"]["execution_uncertain"]
            assert call("AsyncVoid")["error"]["code"] == "unsupported_async_method"
            assert call("Increment")["data"]["result"] == "1"
            assert client.request("invoke_method", {"type_name": "BubbleHarness", "method_name": "Count"}, pid=second["pid"])["data"]["result"] == "0"
            assert client.request("inspect_scene", {"max_objects": 10}, pid=pid)["ok"]
            assert client.request("execute_menu", {"menu_path": "Test/Okay"}, pid=pid)["ok"]
            assert client.request("execute_menu", {"menu_path": "Test/Missing"}, pid=pid)["error"]["code"] == "menu_unavailable"

            def raw(**updates):
                request = {"protocol": 1, "token": first["token"], "operation": "invoke_method", "arguments": {"type_name": "BubbleHarness", "method_name": "Increment"}, "timeout": 3, "expires_at": time.time() + 3}
                request.update(updates)
                with socket.create_connection(("127.0.0.1", first["port"]), timeout=3) as connection:
                    connection.sendall(json.dumps(request).encode() + b"\n")
                    return json.loads(connection.makefile("rb").readline())
            assert raw(token="invalid")["error"]["code"] == "authentication_failed"
            assert raw(expires_at=1)["error"]["code"] == "expired"
            assert raw(operation="unknown")["error"]["code"] == "unknown_operation"
            assert call("Count")["data"]["result"] == "1"

            # A running task may finish after the caller times out. A queued task
            # behind it must expire without executing once the main thread frees.
            pause = []
            worker = threading.Thread(target=lambda: pause.append(call("Pause", "700", timeout=.25)))
            worker.start()
            marker = scratch / "pause-started"
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            assert marker.exists()
            queued = call("Increment", timeout=.1)
            assert queued["error"]["code"] == "timeout" and not queued["error"]["execution_uncertain"]
            worker.join(3)
            assert pause[0]["error"]["execution_uncertain"]
            time.sleep(.75)
            assert call("Count")["data"]["result"] == "1", "Expired queued mutation ran"
            assert call("SetCompiling", "true")["ok"]
            assert call("Increment")["error"]["code"] == "editor_busy"
            assert client.request("status", pid=pid)["data"]["is_compiling"]

            # The other independent Editor remains callable and cleans discovery
            # before reload. Its disappearance never routes to the first one.
            reload_result = client.request("invoke_method", {"type_name": "BubbleHarness", "method_name": "Reload"}, pid=second["pid"])
            assert reload_result["ok"]
            assert not (scratch / "sessions" / (str(second["pid"]) + ".json")).exists()
            assert client.request("status", pid=second["pid"])["error"]["code"] == "session_selection"
            print("PASS: production C# transport, auth, independent instances, main-thread method, exceptions, expiry, queued cancellation, running timeout, busy-state guard and reload cleanup (Unity API stubs)")
        finally:
            for process in processes:
                process.terminate()
                process.communicate(timeout=10)


if __name__ == "__main__":
    main()
