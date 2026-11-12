import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from build_submission import build
from solution import data_directory, run_batch
from submission_model import ModelAdapter, Settings


class FakeModel:
    def __init__(self):
        self.dialogues = []

    def generate_prompt(self, messages):
        payload = json.loads(messages[-1]["content"])
        self.dialogues.append(payload["dialogue"])
        return json.dumps({"action": "answer", "answer": "Требуется оценка кровли.",
                           "source_ids": [payload["knowledge_base"][0]["id"]]})


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with ZipFile(self.root / "knowledge-base.zip", "w") as archive:
            archive.writestr("solar.md", "# Солнечные панели\nДля установки на крыше нужна оценка кровли.")
        self.questions([
            ("001", "Пользователь: Нужны солнечные панели.\nАссистент: Где установить?\nПользователь: На крыше."),
            ("002", "Можно установить солнечные панели?"),
        ])

    def questions(self, rows):
        with (self.root / "questions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["id", "question"])
            writer.writerows(rows)

    def test_batch_preserves_ids_and_isolates_histories(self):
        model = FakeModel()
        output = self.root / "submission.csv"
        with patch.dict(os.environ, {"KNOWLEDGE_BASE_PATH": str(self.root / "knowledge-base.zip")}):
            self.assertEqual(run_batch(self.root, output, model=model), 2)
        with output.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["id"] for r in rows], ["001", "002"])
        self.assertEqual([len(d) for d in model.dialogues], [3, 1])
        self.assertTrue(all(r["answer"] for r in rows))

    def test_missing_and_empty_data_dir_use_default_folder(self):
        with tempfile.TemporaryDirectory() as cwd:
            previous = Path.cwd()
            try:
                os.chdir(cwd)
                data = Path("data")
                data.mkdir()
                (data / "questions.csv").write_text("id,question\n", encoding="utf-8")
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(data_directory(), data)
                with patch.dict(os.environ, {"DATA_DIR": ""}):
                    self.assertEqual(data_directory(), data)
                    self.assertEqual(data_directory(self.root), self.root)
            finally:
                os.chdir(previous)

    def test_missing_questions_has_actionable_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "--data-dir"):
            run_batch(self.root / "missing", model=FakeModel())

    def test_failed_model_does_not_publish_partial_csv(self):
        model = FakeModel()
        model.generate_prompt = lambda _: (_ for _ in ()).throw(RuntimeError("offline"))
        output = self.root / "submission.csv"
        with self.assertRaises(RuntimeError):
            run_batch(self.root, output, model=model)
        self.assertFalse(output.exists())

    def test_flat_archive_imports_without_original_packages(self):
        archive = build(self.root / "submission.zip")
        unpacked = self.root / "unpacked"
        with ZipFile(archive) as zipfile:
            self.assertTrue(all("/" not in name for name in zipfile.namelist()))
            self.assertTrue(all(name.endswith(".py") or name == "requirements.txt"
                                for name in zipfile.namelist()))
            zipfile.extractall(unpacked)
        script = '''import json
from solution import run_batch
class Model:
    def generate_prompt(self, messages):
        p=json.loads(messages[-1]['content'])
        return json.dumps({'action':'answer','answer':'Нужна оценка кровли.',
                           'source_ids':[p['knowledge_base'][0]['id']]})
run_batch('..', model=Model())
'''
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "KNOWLEDGE_BASE_PATH": str(self.root / "knowledge-base.zip")}
        completed = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", script], cwd=unpacked,
                                   env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((unpacked / "submission.csv").exists())

    def test_transport_preserves_system_prompt(self):
        import httpx
        captured = []
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        adapter = ModelAdapter(Settings("test-key", "https://example.invalid/v1", "test-model"))
        adapter._client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(adapter.close)
        messages = [{"role": "system", "content": "RAG rules"}, {"role": "user", "content": "data"}]
        self.assertEqual(adapter.generate_prompt(messages), "{}")
        self.assertEqual(captured[0]["messages"], messages)

    def test_cli_without_arguments_in_flat_archive(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                payload = json.loads(body["messages"][-1]["content"])
                answer = json.dumps({"action": "answer", "answer": "Нужна оценка кровли.",
                                     "source_ids": [payload["knowledge_base"][0]["id"]]})
                data = json.dumps({"choices": [{"message": {"content": answer}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            unpacked = self.root / "cli"
            with ZipFile(build(self.root / "cli.zip")) as archive:
                archive.extractall(unpacked)
            env = {**os.environ, "DATA_DIR": str(self.root), "LLM_API_KEY": "test",
                   "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                   "LLM_MODEL": "test", "PYTHONDONTWRITEBYTECODE": "1",
                   "KNOWLEDGE_BASE_PATH": str(self.root / "knowledge-base.zip")}
            completed = subprocess.run([sys.executable, "-B", "-X", "utf8", "solution.py"], cwd=unpacked,
                                       env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with (unpacked / "submission.csv").open(encoding="utf-8", newline="") as stream:
                self.assertEqual([r["id"] for r in csv.DictReader(stream)], ["001", "002"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_rate_limit_retries_are_bounded(self):
        import httpx
        responses = [429, 503, 429, 429]
        def respond(request):
            return httpx.Response(responses.pop(0), headers={"Retry-After": "2"})
        adapter = ModelAdapter(Settings("key", "https://example.invalid/v1", "model"))
        adapter._client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(adapter.close)
        with patch("submission_model.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                adapter.generate_prompt([])
        self.assertEqual(sleep.call_count, 3)
        self.assertEqual(responses, [])

    def test_empty_completion_retries_without_using_reasoning_as_answer(self):
        import httpx
        choices = [
            {"finish_reason": "stop", "message": {"content": None, "reasoning_content": "internal"}},
            {"finish_reason": "stop", "message": {"content": "{}"}},
        ]
        adapter = ModelAdapter(Settings("key", "https://example.invalid/v1", "model"))
        adapter._client = httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [choices.pop(0)]})))
        self.addCleanup(adapter.close)
        with patch("submission_model.time.sleep"):
            self.assertEqual(adapter.generate_prompt([]), "{}")
        self.assertEqual(choices, [])

    def test_truncated_completion_gets_larger_budget(self):
        import httpx
        budgets = []
        def respond(request):
            budgets.append(json.loads(request.content)["max_tokens"])
            choice = ({"finish_reason": "length", "message": {"content": "{partial"}}
                      if len(budgets) == 1 else
                      {"finish_reason": "stop", "message": {"content": "{}"}})
            return httpx.Response(200, json={"choices": [choice]})
        adapter = ModelAdapter(Settings("key", "https://example.invalid/v1", "model"))
        adapter._client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(adapter.close)
        with patch("submission_model.time.sleep"):
            self.assertEqual(adapter.generate_prompt([]), "{}")
        self.assertEqual(budgets, [1500, 3000])

    def test_persistent_empty_completion_has_diagnostics_and_bounded_retries(self):
        import httpx
        requests = []
        def respond(request):
            requests.append(json.loads(request.content)["max_tokens"])
            return httpx.Response(200, json={"choices": [{"finish_reason": "length",
                                   "message": {"content": "", "reasoning_content": "internal"}}],
                                   "usage": {"completion_tokens": 6000}})
        adapter = ModelAdapter(Settings("key", "https://example.invalid/v1", "model"))
        adapter._client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(adapter.close)
        with patch("submission_model.time.sleep"):
            with self.assertRaisesRegex(ValueError, "finish_reason=length, completion_tokens=6000"):
                adapter.generate_prompt([])
        self.assertEqual(requests, [1500, 3000, 6000])


if __name__ == "__main__":
    unittest.main()
