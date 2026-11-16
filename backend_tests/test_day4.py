import json
import tempfile
import threading
import httpx
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend.service import ChatService
from backend.store import SessionStore
from backend.config import Settings
from backend.llm import ModelAdapter
from orchestration import process_message


class Index:
    def search(self, messages, top_k=5):
        return []


class Model:
    def generate_prompt(self, messages):
        return json.dumps({"action": "clarify", "answer": "Уточните задачу.", "source_ids": []})


class DayFourTests(unittest.TestCase):
    def test_temporary_model_failure_is_retried(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, request=request, json={
                'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]})
        adapter = ModelAdapter(Settings('key', 'https://example.invalid/v1', 'model'))
        with patch('backend.llm.OpenAI') as factory:
            from openai import OpenAI
            factory.side_effect = lambda **kwargs: OpenAI(
                **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            self.assertEqual(adapter.generate_prompt([]), 'ok')
            self.assertEqual(len(calls), 2)
        adapter.close()

    def test_metrics_for_consultation_and_contact_collection(self):
        result = process_message('Нужна помощь', model=Model(), index=Index())
        self.assertEqual(result['metrics']['model_calls'], 1)
        self.assertGreaterEqual(result['metrics']['search_ms'], 0)
        self.assertGreaterEqual(result['metrics']['generation_ms'], 0)
        result = process_message('Хочу оформить заявку', model=Model(), index=Index())
        self.assertEqual(result['metrics']['model_calls'], 0)

    def test_concurrent_sessions_and_failed_turn_are_isolated(self):
        class ConcurrentModel(Model):
            def generate_prompt(self, messages):
                payload = json.loads(messages[-1]['content'])
                text = payload['dialogue'][-1]['content']
                if text == 'failure':
                    raise RuntimeError('temporary')
                return super().generate_prompt(messages)

        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / 'sessions.db')
            service = ChatService(ConcurrentModel(), store)
            barrier = threading.Barrier(3)
            def chat(session, message):
                barrier.wait(timeout=10)
                try:
                    return service.chat(message, session)
                except RuntimeError:
                    return None
            with patch('backend.service.get_index', return_value=Index()):
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(chat, 'one', 'first'), pool.submit(chat, 'two', 'second'),
                               pool.submit(chat, 'three', 'failure')]
                    results = [future.result(timeout=20) for future in futures]
            self.assertIsNone(results[2])
            self.assertEqual(store.get('one')['messages'][0]['content'], 'first')
            self.assertEqual(store.get('two')['messages'][0]['content'], 'second')
            self.assertIsNone(store.get('three'))
            self.assertGreaterEqual(results[0]['metrics']['total_ms'], 0)
