import concurrent.futures
import json
from pathlib import Path
import sys
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from broker import Broker


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = Broker("photoshop")
        self.pool = concurrent.futures.ThreadPoolExecutor()

    def tearDown(self):
        self.broker.close()
        self.pool.shutdown()

    def post(self, endpoint, data, token=None):
        req = urllib.request.Request(
            "http://127.0.0.1:%s%s" % (self.broker.http.server_port, endpoint),
            json.dumps(data).encode(), headers={
                "Authorization": "Bearer " + (self.broker.token if token is None else token),
                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    def register(self, name="shot.psd"):
        return self.post("/register", {"info": {"app": "photoshop", "version": "26.2",
            "targets": [{"id": "project-1", "name": name, "path": "C:/work/" + name}]}})["data"]["session_id"]

    def queued(self, sid, timeout=1):
        future = self.pool.submit(self.broker.request, "save_project", {"project_id": "project-1"}, sid, timeout)
        deadline = time.time() + 1
        while not self.broker.jobs and time.time() < deadline:
            time.sleep(.002)
        return future

    def poll(self, sid):
        return self.post("/poll", {"session_id": sid, "info": {"app": "photoshop", "targets": []}})

    def test_token_required(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/register", {}, "bad")
        self.assertEqual(caught.exception.code, 401)

    def test_wrong_application_rejected(self):
        result = self.post("/register", {"info": {"app": "wrong_app"}})
        self.assertFalse(result["ok"])
        self.assertFalse(self.broker.clients)

    def test_multi_panel_no_silent_selection(self):
        self.register()
        self.register()
        self.assertEqual(self.broker.request("status")["error"]["code"], "selection")
        self.assertEqual(self.broker.sessions("shot")["selection"]["status"], "ambiguous")

    def test_unique_exact_match(self):
        sid = self.register()
        self.assertEqual(self.broker.sessions("shot")["selection"]["selected"]["session_id"], sid)
        self.assertEqual(self.broker.sessions("sho")["selection"]["status"], "not_found")
        self.assertNotIn(self.broker.token, json.dumps(self.broker.sessions()))

    def test_expired_undelivered_not_replayed(self):
        sid = self.register()
        result = self.queued(sid, .03).result(1)
        self.assertFalse(result["error"]["execution_uncertain"])
        self.assertIsNone(self.poll(sid)["data"])

    def test_delivery_is_at_most_once(self):
        sid = self.register()
        future = self.queued(sid)
        job = self.poll(sid)["data"]
        self.assertIsNone(self.poll(sid)["data"])
        self.post("/result", {"session_id": sid, "request_id": job["request_id"], "response": {"ok": True, "data": 7}})
        self.assertEqual(future.result(1)["data"], 7)

    def test_other_panel_cannot_complete_request(self):
        sid, other = self.register(), self.register("other.psd")
        future = self.queued(sid, .2)
        job = self.poll(sid)["data"]
        result = self.post("/result", {"session_id": other, "request_id": job["request_id"], "response": {"ok": True}})
        self.assertFalse(result["ok"])
        self.assertTrue(future.result(1)["error"]["execution_uncertain"])

    def test_busy_panel_not_expired(self):
        sid = self.register()
        future = self.queued(sid, .3)
        job = self.poll(sid)["data"]
        self.broker.clients[sid]["seen"] = time.time() - 30
        self.broker.sessions()
        self.assertIn(sid, self.broker.clients)
        self.post("/result", {"session_id": sid, "request_id": job["request_id"], "response": {"ok": True}})
        self.assertTrue(future.result(1)["ok"])

    def test_truncated_targets_never_select_unique(self):
        sid = self.register()
        self.post("/poll", {"session_id": sid, "info": {"targets": [{"id": "x", "name": "a"}] * 101}})
        self.assertEqual(self.broker.sessions("a")["selection"]["status"], "incomplete")

    def test_disconnect_cancels_queue(self):
        sid = self.register()
        future = self.queued(sid)
        self.post("/unregister", {"session_id": sid})
        self.assertFalse(future.result(1)["error"]["execution_uncertain"])
        self.assertFalse(self.broker.sessions()["data"])

    def test_invalid_timeout_and_unknown_session(self):
        self.assertFalse(self.broker.request("status", timeout=True)["ok"])
        self.assertFalse(self.broker.request("status", session_id="unknown")["ok"])

    def test_large_request_not_queued(self):
        sid = self.register()
        self.assertFalse(self.broker.request("x", {"x": "x" * 1048576}, sid)["ok"])
        self.assertFalse(self.broker.jobs)


if __name__ == "__main__":
    unittest.main()
