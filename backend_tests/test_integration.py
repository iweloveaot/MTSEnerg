import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError, APIConnectionError, APIStatusError

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.llm import ModelAdapter, ServiceError
from backend.service import process_message
from solution import solve


class FakeModel:
    def __init__(self):
        self.calls = []
        self.error = None

    def generate(self, messages):
        if self.error:
            raise self.error
        self.calls.append(messages)
        return "Уточните задачу, пожалуйста."

    def check(self):
        self.generate([{"role": "user", "content": "Проверка"}])

    def close(self):
        pass


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings("key", "https://example.invalid/v1", "model",
                                 database=str(Path(self.tmp.name) / "sessions.db"))
        self.model = FakeModel()
        self.app = create_app(self.settings, self.model)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def chat(self, message, session="one"):
        return self.client.post("/api/chat", json={"message": message, "session_id": session})

    def test_static_frontend_and_health(self):
        for path in ("/", "/app.js", "/styles.css", "/api/health", "/api/ready"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn('id="chat-form"', self.client.get("/").text)
        self.assertEqual(self.client.get("/.env").status_code, 404)

    def test_response_history_and_isolation(self):
        first = self.chat("У нас три склада").json()
        self.assertEqual(first["session_id"], "one")
        self.assertGreaterEqual(first["processing_time_ms"], 0)
        self.assertEqual(first["sources"], [])
        self.assertIsInstance(first["answer"], str)
        self.chat("Нужен учёт")
        self.assertEqual(len(self.model.calls[-1]), 3)
        self.chat("Новый разговор", "two")
        self.assertEqual(len(self.model.calls[-1]), 1)

    def test_history_survives_restart(self):
        self.chat("Первое сообщение")
        with TestClient(create_app(self.settings, self.model)) as client:
            client.post("/api/chat", json={"session_id": "one", "message": "Продолжение"})
        self.assertEqual(self.model.calls[-1][0]["content"], "Первое сообщение")

    def test_failed_turn_not_committed_and_recovery(self):
        for code, status in (("model_timeout", 504), ("model_unavailable", 503),
                             ("model_auth_error", 503), ("invalid_model_response", 502)):
            self.model.error = ServiceError(code, "Попробуйте позже", status)
            response = self.chat("Не сохранять")
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["error"]["code"], code)
            self.assertEqual(self.client.get("/api/ready").status_code, status)
            self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.model.error = None
        self.assertEqual(self.chat("Работаем").status_code, 200)
        self.assertEqual(len(self.model.calls[-1]), 1)

    def test_validation_and_generated_session(self):
        for message in ("", "   ", "x" * 10001):
            self.assertEqual(self.chat(message).status_code, 422)
        response = self.client.post("/api/chat", json={"message": "Привет"})
        self.assertTrue(response.json()["session_id"])
        self.assertEqual(self.chat("Привет", "../bad").status_code, 422)

    def test_application_opt_in_and_ready(self):
        contacts = "Меня зовут Анна Иванова. Компания Ромашка. Телефон 89991234567."
        self.assertFalse(self.chat(contacts).json()["application"]["ready"])
        data = self.chat("Хочу оформить заявку").json()
        self.assertTrue(data["application"]["ready"])
        self.assertIn("отправка менеджеру пока не подключена", data["answer"])

    def test_application_refusal_continues_consultation(self):
        self.chat("Хочу оформить заявку")
        result = self.chat("Не хочу оставлять телефон").json()
        self.assertEqual(result["application"]["status"], "declined")
        self.assertEqual(result["answer"], "Уточните задачу, пожалуйста.")

    def test_solution_uses_shared_handler_without_session_leak(self):
        with patch("solution.ModelAdapter", return_value=self.model), patch(
            "solution.Settings.from_env", return_value=self.settings,
        ):
            first = solve("Первый вопрос")
            second = solve("Второй вопрос")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(len(self.model.calls[-1]), 1)

    def test_shared_handler_preserves_history(self):
        history = [{"role": "user", "content": "Хочу оформить заявку"}]
        result = process_message("Меня зовут Анна Иванова", history=history, model=self.model)
        self.assertEqual(len(history), 1)
        self.assertIn("телефон", result["answer"])

    def test_unconfigured_model(self):
        with self.assertRaises(ServiceError) as caught:
            ModelAdapter(Settings("", "", "")).check()
        self.assertEqual(caught.exception.code, "model_not_configured")

    def test_adapter_translates_provider_failures(self):
        adapter = ModelAdapter(self.settings)
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        failures = [
            (APITimeoutError(request=request), "model_timeout", 504),
            (APIConnectionError(request=request), "model_unavailable", 503),
            (APIStatusError("secret provider body", response=httpx.Response(401, request=request), body=None),
             "model_auth_error", 503),
        ]
        for failure, code, status in failures:
            with patch.object(adapter, "_get_client") as client:
                client.return_value.chat.completions.create.side_effect = failure
                with self.assertRaises(ServiceError) as caught:
                    adapter.generate([])
            self.assertEqual((caught.exception.code, caught.exception.status), (code, status))
            self.assertNotIn("secret provider body", str(caught.exception))

    def test_adapter_rejects_empty_model_answer(self):
        adapter = ModelAdapter(self.settings)
        with patch.object(adapter, "_get_client") as client:
            client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" "))],
            )
            with self.assertRaises(ServiceError) as caught:
                adapter.generate([])
        self.assertEqual(caught.exception.code, "invalid_model_response")


if __name__ == "__main__":
    unittest.main()
