
import unittest

from application_agent import (
    ApplicationAgentInput,
    Contacts,
    Message,
    run_application_agent,
)

from application_agent.serializer import result_to_dict


class FullApplicationFlowTests(unittest.TestCase):

    def test_consultation_to_ready_application(self):
        """
        Клиент обсуждает задачу, затем
        оставляет контакты для менеджера.
        """

        messages = [
            Message(
                role="user",
                content=(
                    "У нас выросли расходы "
                    "на электроэнергию."
                ),
            ),
            Message(
                role="assistant",
                content=(
                    "Какая у вас ценовая категория?"
                ),
            ),
            Message(
                role="user",
                content=(
                    "Четвёртая. Хотим разобраться "
                    "в причинах роста расходов."
                ),
            ),
            Message(
                role="user",
                content="Меня зовут Анна Иванова.",
            ),
            Message(
                role="user",
                content="Компания Ромашка.",
            ),
            Message(
                role="user",
                content=(
                    "Мой телефон 8 (999) 123-45-67."
                ),
            ),
        ]

        result = run_application_agent(
            ApplicationAgentInput(
                session_id="integration-1",
                messages=messages,
                current_draft=Contacts(),
                application_requested=True,
            )
        )

        data = result_to_dict(result)

        self.assertTrue(data["ready"])
        self.assertEqual(data["status"], "ready")

        self.assertEqual(
            data["contacts"]["full_name"],
            "Анна Иванова",
        )
        self.assertEqual(
            data["contacts"]["company"],
            "Ромашка",
        )
        self.assertEqual(
            data["contacts"]["phone"],
            "+79991234567",
        )

        self.assertIn(
            "выросли расходы",
            data["summary"]["problem"],
        )

    def test_client_corrects_contacts(self):
        """
        Новые контакты должны заменять
        старые данные клиента.
        """

        messages = [
            Message(
                role="user",
                content="Меня зовут Анна Иванова.",
            ),
            Message(
                role="user",
                content="Компания Ромашка.",
            ),
            Message(
                role="user",
                content=(
                    "Телефон 8 (999) 123-45-67."
                ),
            ),
            Message(
                role="user",
                content=(
                    "Исправление: меня зовут "
                    "Мария Петрова."
                ),
            ),
            Message(
                role="user",
                content=(
                    "Мой номер другой: "
                    "8 (999) 555-44-33."
                ),
            ),
        ]

        result = run_application_agent(
            ApplicationAgentInput(
                session_id="integration-2",
                messages=messages,
                current_draft=Contacts(),
                application_requested=True,
            )
        )

        self.assertEqual(
            result.contacts.full_name,
            "Мария Петрова",
        )
        self.assertEqual(
            result.contacts.phone,
            "+79995554433",
        )

        self.assertTrue(result.ready)

    def test_client_refuses_phone(self):
        """
        Клиент может продолжить общение,
        не оставляя номер телефона.
        """

        messages = [
            Message(
                role="user",
                content=(
                    "У нас три склада и около "
                    "сорока счётчиков."
                ),
            ),
            Message(
                role="assistant",
                content=(
                    "Можно подготовить "
                    "предварительную оценку."
                ),
            ),
            Message(
                role="user",
                content=(
                    "Я пока не готов оставлять телефон."
                ),
            ),
        ]

        result = run_application_agent(
            ApplicationAgentInput(
                session_id="integration-3",
                messages=messages,
                current_draft=Contacts(),
            )
        )

        self.assertEqual(result.status, "declined")
        self.assertFalse(result.ready)
        self.assertIsNone(result.next_question)

        self.assertIn(
            "три склада",
            result.summary.problem,
        )


if __name__ == "__main__":
    unittest.main()
