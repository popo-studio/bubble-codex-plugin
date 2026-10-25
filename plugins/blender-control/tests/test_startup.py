import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class StartupTests(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('bubble_startup_fixture',ROOT/'runtime/startup.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 def test_registration_is_deferred_idempotent_and_cancelled(self):
  registered={}
  timers=types.SimpleNamespace(register=lambda fn,**kw:registered.update({fn:kw}),is_registered=lambda fn:fn in registered,unregister=lambda fn:registered.pop(fn))
  bpy=types.SimpleNamespace(app=types.SimpleNamespace(background=False,timers=timers))
  with patch.dict(sys.modules,{'bpy':bpy}):
   m=self.load();m.register();m.register();self.assertEqual(len(registered),1);self.assertEqual(next(iter(registered.values()))['first_interval'],.5);m.unregister();self.assertFalse(registered)
 def test_background_does_not_autostart(self):
  with patch.dict(sys.modules,{'bpy':types.SimpleNamespace(app=types.SimpleNamespace(background=True))}):self.load().register()

class ParameterTests(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('bubble_ops_fixture',ROOT/'runtime/operations.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
 def test_nonfinite_bool_and_out_of_range(self):
  for v in [float('nan'),float('inf'),True,1e20]:
   with self.assertRaises(ValueError):self.m.number(v)
 def test_vector_and_name_validation(self):
  for v in [[1,2],[1,2,float('nan')]]:
   with self.assertRaises(ValueError):self.m.vector(v)
  for v in ['', 'bad\nname','x'*64,'中'*30]:
   with self.assertRaises(ValueError):self.m.label(v)
 def test_previous_session_snapshot_rejected_with_identical_pid_and_scene(self):
  collection=types.SimpleNamespace(name='Scene Collection',session_uid=1,objects=[],children=[])
  bpy=types.SimpleNamespace(data=types.SimpleNamespace(objects=[],collections=[],filepath='',is_dirty=False),context=types.SimpleNamespace(scene=types.SimpleNamespace(name='Scene',collection=collection,library=None,override_library=None)))
  previous=self.m.state(bpy)
  self.m.guard(bpy,{'pid':os.getpid(),'expected_snapshot':previous['snapshot']})
  self.m.begin_session()
  current=self.m.state(bpy)
  self.assertEqual(previous['scene'],current['scene'])
  self.assertNotEqual(previous['snapshot'],current['snapshot'])
  with self.assertRaisesRegex(ValueError,'Scene changed'):
   self.m.guard(bpy,{'pid':os.getpid(),'expected_snapshot':previous['snapshot']})
  self.m.guard(bpy,{'pid':os.getpid(),'expected_snapshot':current['snapshot']})

class BridgeLifecycleTests(unittest.TestCase):
 def test_timer_registration_failure_closes_bound_socket(self):
  sys.path.insert(0,str(ROOT/'runtime'))
  import bridge
  from unittest.mock import Mock
  listener=Mock();bpy=types.SimpleNamespace(app=types.SimpleNamespace(version=(4,5,3),timers=types.SimpleNamespace(register=Mock(side_effect=RuntimeError('fixture timer failure')))))
  with patch.dict(sys.modules,{'bpy':bpy}),patch.object(bridge,'Bridge',return_value=listener):
   with self.assertRaises(RuntimeError):bridge.start()
  listener.server_close.assert_called_once()
 def test_start_rotates_nonce_but_already_running_start_does_not(self):
  sys.path.insert(0,str(ROOT/'runtime'))
  import bridge
  from unittest.mock import Mock
  bpy=types.SimpleNamespace(app=types.SimpleNamespace(version=(4,5,3)))
  with patch.dict(sys.modules,{'bpy':bpy}),patch.object(bridge,'_bridge',None),patch.object(bridge,'Bridge',side_effect=RuntimeError('fixture bind failure')):
   original=bridge._operations.SESSION_NONCE
   with self.assertRaises(RuntimeError):bridge.start()
   first=bridge._operations.SESSION_NONCE
   self.assertNotEqual(original,first)
   with self.assertRaises(RuntimeError):bridge.start()
   self.assertNotEqual(first,bridge._operations.SESSION_NONCE)
  active=types.SimpleNamespace(server_address=('127.0.0.1',12345))
  with patch.object(bridge,'_bridge',active):
   nonce=bridge._operations.SESSION_NONCE
   self.assertTrue(bridge.start()['already_running'])
   self.assertEqual(nonce,bridge._operations.SESSION_NONCE)
