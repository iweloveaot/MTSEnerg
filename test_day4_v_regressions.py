"""Офлайн-регрессии агента заявки участника В (без LLM и сети).

Запуск: .venv/bin/python -m unittest -v test_day4_v_regressions.py
Две известные неточности резюме временно помечены expectedFailure:
исправление числа счётчиков и смена главной темы.
"""
import unittest

from application_agent import ApplicationAgentInput, Message, run_application_agent
from application_agent.serializer import result_to_dict


CONTACTS = "Меня зовут Анна Иванова. Компания Ромашка. Телефон 89991234567."


def application(*user_texts, consent=True):
    data = result_to_dict(run_application_agent(ApplicationAgentInput(
        session_id="day4-v-test",
        messages=[Message(role="user", content=text) for text in user_texts],
        application_requested=consent,
    )))
    return data


class Day4ParticipantVRegressions(unittest.TestCase):
    def test_valid_application(self):
        result = application("Нужно учитывать электроэнергию на складе.", CONTACTS)
        self.assertTrue(result["ready"])
        self.assertEqual(result["contacts"]["phone"], "+79991234567")

    def test_contacts_alone_are_not_consent(self):
        result = application(CONTACTS, consent=False)
        self.assertFalse(result["ready"])
        self.assertIsNone(result["next_question"])

    def test_refusal_stops_contact_questions(self):
        result = application("Хочу оформить заявку", "Я не хочу оставлять телефон")
        self.assertFalse(result["ready"])
        self.assertTrue(result["contact_collection_declined"])
        self.assertIsNone(result["next_question"])

    def test_unknown_power_is_not_invented(self):
        result = application(
            "Нужно учитывать потребление, но мощность оборудования неизвестна.", CONTACTS
        )
        summary = " ".join(str(value) for value in result["summary"].values())
        self.assertNotIn("кВт", summary)
        self.assertIn("неизвестна", summary)

    def test_corrected_meter_count_replaces_obsolete_value(self):
        result = application(
            "Нужно контролировать 10 счётчиков.",
            "Уточняю: не 10, а 15 счётчиков.",
            CONTACTS,
        )
        summary = " ".join(str(value) for value in result["summary"].values())
        self.assertIn("15 счётчиков", summary)
        self.assertNotIn("контролировать 10 счётчиков", summary.lower())

    def test_meter_count_12_corrected_to_18(self):
        result = application(
            "Хотим следить за 12 счётчиками.",
            "Поправка: не 12, а 18 счётчиков.",
            CONTACTS,
        )
        summary = " ".join(str(value) for value in result["summary"].values())
        self.assertIn("18 счётчиками", summary)
        self.assertNotIn("12 счётчиками", summary)

    def test_other_numbers_not_rewritten(self):
        result = application(
            "На 3 складах контролируем 10 счётчиков.",
            "Уточняю: не 10, а 15 счётчиков.",
            CONTACTS,
        )
        summary = result["summary"]["problem"]
        self.assertIn("3 складах", summary)
        self.assertIn("15 счётчиков", summary)

    def test_nonexplicit_new_detail_preserves_main_topic(self):
        result = application(
            "Хочу установить солнечные панели.",
            "Ещё нужно проверить расход электроэнергии.",
            CONTACTS,
        )
        self.assertIn("солнечные панели", result["summary"]["problem"])

    def test_main_topic_changes_when_client_explicitly_switches(self):
        result = application(
            "Хочу установить солнечные панели.",
            "Теперь главная задача — мониторинг энергопотребления.",
            CONTACTS,
        )
        self.assertIn("мониторинг", result["summary"]["problem"].lower())


if __name__ == "__main__":
    unittest.main()
