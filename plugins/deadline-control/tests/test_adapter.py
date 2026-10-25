import bz2
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import adapter

JOB = "5b747b30c3ca512de42d01d2"


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.command = self.root / "deadlinecommand.exe"
        self.command.write_bytes(b"fake")
        self.j = self.root / "job.job"
        self.p = self.root / "plugin.job"
        self.j.write_text("Plugin=MayaBatch\nName=hero\nFrames=1-10\nInitialStatus=Suspended\n")
        self.p.write_text("SceneFile=D:/hero.ma\nVersion=2027\n")
        adapter._plans.clear()

    def tearDown(self):
        self.directory.cleanup()

    def submit(self, **kwargs):
        return adapter.submit(str(self.j), str(self.p), command=str(self.command), **kwargs)

    def test_absent_status_is_explicit_not_transport_error(self):
        result = adapter.status(str(self.root / "missing.exe"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["data"]["available"])
        self.assertFalse(result["data"]["farm_checked"])

    def test_explicit_path_does_not_fallback(self):
        with self.assertRaises(ValueError):
            adapter.discover("-Version")

    def test_ini_keeps_equals_and_sections(self):
        self.assertEqual(adapter.ini("[x]\nName=a=b\n[y]\nStatus=Failed"), [{"section":"x","Name":"a=b"},{"section":"y","Status":"Failed"}])

    def test_unsectioned_jobs_and_unrecognized_output(self):
        self.assertEqual(adapter.ini("Name=a\nID=1\n\nName=b\nID=2"),[{"Name":"a","ID":"1"},{"Name":"b","ID":"2"}])
        for text in ["Name=a\nName=b", "Connection failed without structured output"]:
            with self.assertRaises(ValueError):
                adapter.ini(text)

    def test_jobs_filter_and_truncation(self):
        with patch.object(adapter, "run", return_value="[a]\nName=a\n[b]\nName=b") as run:
            result = adapter.jobs("Failed", "artist", 1, str(self.command))
        self.assertTrue(result["data"]["truncated"])
        self.assertEqual(run.call_args.args[1], ["-GetJobsFilterIniAnd","Status=Failed","UserName=artist"])

    def test_bad_job_never_invokes_cli(self):
        with patch.object(adapter, "run") as run:
            self.assertFalse(adapter.job("-DeleteJob all", str(self.command))["ok"])
            run.assert_not_called()

    def test_submission_preview_has_no_writes_or_process(self):
        before = sorted(p.name for p in self.root.iterdir())
        with patch.object(adapter, "run") as run:
            result = self.submit()
            run.assert_not_called()
        self.assertTrue(result["data"]["requires_confirmation"])
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))

    def test_confirm_without_token_blocked(self):
        with patch.object(adapter, "run") as run:
            self.assertFalse(self.submit(confirmed=True)["ok"])
            run.assert_not_called()

    def test_changed_info_invalidates_preview(self):
        token = self.submit()["data"]["preview_token"]
        self.j.write_text("Plugin=MayaBatch\nName=changed\n")
        with patch.object(adapter, "run") as run:
            self.assertFalse(self.submit(confirmed=True,preview_token=token)["ok"])
            run.assert_not_called()

    def test_submission_stages_reviewed_bytes_and_token_one_use(self):
        token = self.submit()["data"]["preview_token"]
        def fake(executable,args,timeout):
            self.assertEqual(Path(args[0]).read_bytes(), self.j.read_bytes())
            self.assertEqual(Path(args[1]).read_bytes(), self.p.read_bytes())
            self.assertNotEqual(Path(args[0]), self.j)
            return f"Result=Success\nJobID={JOB}\n"
        with patch.object(adapter, "run", side_effect=fake) as run:
            self.assertTrue(self.submit(confirmed=True,preview_token=token)["data"]["submitted"])
            self.assertFalse(self.submit(confirmed=True,preview_token=token)["ok"])
            self.assertEqual(run.call_count,1)

    def test_aux_change_invalidates_preview(self):
        aux = self.root / "scene.ma"; aux.write_text("original")
        token = self.submit(auxiliary_files=[str(aux)])["data"]["preview_token"]
        aux.write_text("changed")
        self.assertFalse(self.submit(auxiliary_files=[str(aux)],confirmed=True,preview_token=token)["ok"])

    def test_duplicate_keys_rejected(self):
        self.j.write_text("Plugin=MayaBatch\nPlugin=CommandLine\n")
        self.assertFalse(self.submit()["ok"])

    def test_unknown_submission_outcome_not_success(self):
        token = self.submit()["data"]["preview_token"]
        with patch.object(adapter, "run", return_value="hello") as run:
            self.assertFalse(self.submit(confirmed=True,preview_token=token)["ok"])
            self.assertEqual(run.call_count,1)

    def test_expired_preview(self):
        token=self.submit()["data"]["preview_token"]
        with patch.object(adapter.time,"monotonic",return_value=adapter.time.monotonic()+601):
            self.assertFalse(self.submit(confirmed=True,preview_token=token)["ok"])

    def test_failed_tasks_use_resume_failed_not_requeue(self):
        before="[0_1-10]\nTaskId=0\nStatus=Failed\nTaskFrameList=1-10"
        after=before.replace("Failed","Queued")
        with patch.object(adapter,"run",return_value=before) as run:
            preview=adapter.retry(JOB,[0],command=str(self.command))
            self.assertEqual(run.call_count,1)
        token=preview["data"]["preview_token"]
        with patch.object(adapter,"run",side_effect=[before,"",after]) as run:
            result=adapter.retry(JOB,[0],confirmed=True,preview_token=token,command=str(self.command))
            self.assertEqual(run.call_args_list[1].args[1],["-ResumeFailedJobTasks",JOB,"0"])
            self.assertTrue(result["data"]["state_verified"])

    def test_retry_state_change_blocks_mutation(self):
        before="[0]\nTaskId=0\nStatus=Failed"
        with patch.object(adapter,"run",return_value=before):
            token=adapter.retry(JOB,[0],command=str(self.command))["data"]["preview_token"]
        with patch.object(adapter,"run",return_value=before.replace("Failed","Rendering")) as run:
            self.assertFalse(adapter.retry(JOB,[0],confirmed=True,preview_token=token,command=str(self.command))["ok"])
            self.assertEqual(run.call_count,1)

    def test_completed_requeue_noop_not_verified(self):
        before="[1]\nTaskId=1\nStatus=Completed"
        with patch.object(adapter,"run",return_value=before):
            token=adapter.retry(JOB,[1],action="requeue_completed",command=str(self.command))["data"]["preview_token"]
        with patch.object(adapter,"run",side_effect=[before,"",before]):
            result=adapter.retry(JOB,[1],action="requeue_completed",confirmed=True,preview_token=token,command=str(self.command))
        self.assertFalse(result["data"]["state_verified"])

    def test_report_bz2_and_missing_are_explicit(self):
        report=self.root/"error.bz2";report.write_bytes(bz2.compress(b"Error: missing texture\n"+b"x"*70000))
        with patch.object(adapter,"run",return_value=str(report)+"\n"+str(self.root/"missing.bz2")):
            result=adapter.reports(JOB,command=str(self.command))["data"]
        self.assertTrue(result["reports"][0]["truncated"])
        self.assertEqual(result["reports"][0]["error_lines"],["Error: missing texture"])
        self.assertIn("error",result["reports"][1])

    def test_process_nonzero_and_text_error(self):
        for code in ["import sys;sys.exit(7)","print('Error: bad job')"]:
            with self.assertRaises(RuntimeError):
                adapter.run(sys.executable,["-c",code])

    def test_process_timeout(self):
        with self.assertRaisesRegex(RuntimeError,"timed out"):
            adapter.run(sys.executable,["-c","import time;time.sleep(5)"],timeout=.1)

    def test_process_output_bound(self):
        with patch.object(adapter,"MAX_OUTPUT",1024):
            with self.assertRaisesRegex(RuntimeError,"exceeds"):
                adapter.run(sys.executable,["-c","print('x'*20000)"])

    def test_process_preserves_literal_arguments(self):
        output=adapter.run(sys.executable,["-c","import sys; print(sys.argv[1])","a & echo hacked"])
        self.assertEqual(output.strip(),"a & echo hacked")

    def test_farm_and_worker_exact_selection(self):
        with patch.object(adapter, 'run', return_value='render-a\nrender-b') as run:
            result = adapter.farm_info('workers', 1, str(self.command))
            self.assertTrue(result['data']['truncated'])
            self.assertEqual(run.call_args.args[1], ['-GetSlaveNames'])
        with patch.object(adapter, 'run', side_effect=['render-a\nrender-b', '[render-a]\nStatus=Idle']) as run:
            self.assertTrue(adapter.worker_info('render-a', str(self.command))['ok'])
            self.assertEqual(run.call_args.args[1], ['-GetSlave', 'render-a', 'True'])
        with patch.object(adapter, 'run') as run:
            self.assertFalse(adapter.worker_info('-DeleteSlave', str(self.command))['ok'])
            run.assert_not_called()
        with patch.object(adapter, 'run', return_value='render-a') as run:
            self.assertFalse(adapter.worker_info('missing', str(self.command))['ok'])
            self.assertEqual(run.call_count, 1)

    def test_job_action_preview_once_and_changed_identity(self):
        before = f'[{JOB}]\nName=hero\nUserName=artist\nPlugin=MayaBatch\nStatus=Rendering'
        with patch.object(adapter, 'run', return_value=before) as run:
            preview = adapter.job_action(JOB, 'suspend', command=str(self.command))
            self.assertEqual(run.call_count, 1)
        token = preview['data']['preview_token']
        with patch.object(adapter, 'run', side_effect=[before, 'Success', before.replace('Rendering', 'Suspended')]) as run:
            result = adapter.job_action(JOB, 'suspend', True, token, str(self.command))
            self.assertTrue(result['data']['state_verified'], result)
            self.assertEqual(run.call_args_list[1].args[1], ['-SuspendJob', JOB])
        with patch.object(adapter, 'run', return_value=before) as run:
            self.assertFalse(adapter.job_action(JOB, 'suspend', True, token, str(self.command))['ok'])
            self.assertEqual(run.call_count, 1)
            token = adapter.job_action(JOB, 'suspend', command=str(self.command))['data']['preview_token']
        with patch.object(adapter, 'run', return_value=before.replace('hero', 'other')) as run:
            self.assertFalse(adapter.job_action(JOB, 'suspend', True, token, str(self.command))['ok'])
            self.assertEqual(run.call_count, 1)

    def test_job_action_resume_noop_not_verified_and_wrong_job_rejected(self):
        before = f'[{JOB}]\nName=hero\nStatus=Suspended'
        with patch.object(adapter, 'run', return_value=before):
            token = adapter.job_action(JOB, 'resume', command=str(self.command))['data']['preview_token']
            result = adapter.job_action(JOB, 'resume', True, token, str(self.command))
            self.assertFalse(result['data']['state_verified'])
        with patch.object(adapter, 'run', return_value=before.replace(JOB, '0' * 24)) as run:
            self.assertFalse(adapter.job_action(JOB, 'resume', command=str(self.command))['ok'])
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
