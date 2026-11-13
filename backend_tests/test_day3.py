import json
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from test_integration import FakeModel


class DayThreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        settings = Settings('key', 'https://example.invalid/v1', 'model',
                            database=str(Path(self.tmp.name) / 'sessions.db'))
        self.settings = settings
        self.model = FakeModel()
        self.client = TestClient(create_app(settings, self.model))
        self.addCleanup(self.client.close)

    def chat(self, session, message):
        return self.client.post('/api/chat', json={'session_id': session, 'message': message})

    def test_archive_application_update_and_close(self):
        session = self.client.post('/api/sessions').json()['session_id']
        self.chat(session, 'Хочу оформить заявку')
        self.chat(session, 'Меня зовут Анна Иванова. Компания Ромашка. Телефон 89991234567.')
        before = self.client.get('/api/sessions/' + session).json()
        self.assertTrue(before['application']['ready'])
        self.chat(session, 'Мой новый телефон 89991112233')
        after = self.client.get('/api/sessions/' + session).json()
        self.assertNotEqual(before['application']['contacts']['phone'], after['application']['contacts']['phone'])
        self.assertEqual(len(self.client.get('/api/sessions').json()['sessions']), 1)
        self.assertEqual(self.client.post('/api/sessions/' + session + '/close').json()['status'], 'closed')
        self.assertEqual(self.chat(session, 'Продолжение').status_code, 409)
        self.assertEqual(self.client.get('/api/sessions/' + session).json()['application'], after['application'])
        self.assertEqual(self.client.get('/api/sessions/missing').status_code, 404)

    def test_offer_and_refusal_reach_consultant(self):
        captured = []
        # A real source is required for an answer, so use a specialist response.
        def specialist(messages):
            captured.append(json.loads(messages[-1]['content']))
            return json.dumps({'action': 'specialist', 'answer': 'Обратитесь к специалисту.',
                               'source_ids': [], 'offer_application': True})
        self.model.generate_prompt = specialist
        first = self.chat('offer', 'Нужен расчёт').json()
        self.assertTrue(first['offer_application'])
        self.chat('offer', 'Хочу оформить заявку')
        refused = self.chat('offer', 'Не хочу оставлять телефон').json()
        self.assertTrue(captured[-1]['contact_collection_declined'])
        self.assertFalse(refused['offer_application'])

    def test_archive_survives_restart_and_sessions_do_not_mix(self):
        self.chat('first', 'Нужны солнечные панели')
        self.chat('first', 'Теперь интересует учёт электричества')
        self.chat('first', 'Вернёмся к солнечным панелям')
        self.chat('second', 'Нужен учёт на складе')
        self.assertEqual(len(self.model.calls[-1]), 1)
        with TestClient(create_app(self.settings, self.model)) as restarted:
            archive = restarted.get('/api/sessions/first').json()
            self.assertEqual(len(archive['messages']), 6)
            self.assertIsNone(archive['application'])
            self.assertEqual(archive['messages'][0]['content'], 'Нужны солнечные панели')
            self.assertEqual(len(restarted.get('/api/sessions').json()['sessions']), 2)

    def test_repeated_request_updates_single_application(self):
        self.chat('same', 'Хочу оформить заявку')
        self.chat('same', 'Меня зовут Анна Иванова. Компания Ромашка. Телефон 89991234567.')
        self.chat('same', 'Хочу оформить заявку')
        archive = self.client.get('/api/sessions/same').json()
        self.assertTrue(archive['application']['ready'])
        import sqlite3
        with closing(sqlite3.connect(self.settings.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM applications').fetchone()[0], 1)
