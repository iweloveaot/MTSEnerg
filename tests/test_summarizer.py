
import unittest

from application_agent.models import Message
from application_agent.summarizer import summarize_dialogue


class SummarizerTests(unittest.TestCase):

    def test_extract_problem(self):
        messages = [
            Message(
                role="user",
                content="У нас выросли счета за электричество.",
            )
        ]

        result = summarize_dialogue(messages)

        self.assertEqual(
            result.problem,
            "У нас выросли счета за электричество.",
        )

    def test_extract_circumstances(self):
        messages = [
            Message(
                role="user",
                content="Хотим снизить расходы.",
            ),
            Message(
                role="user",
                content="У нас три склада.",
            ),
        ]

        result = summarize_dialogue(messages)

        self.assertEqual(
            result.circumstances,
            "У нас три склада.",
        )

    def test_extract_assistant_explanation(self):
        messages = [
            Message(
                role="user",
                content="Счета стали больше.",
            ),
            Message(
                role="assistant",
                content=(
                    "Предлагаю сравнить потребление "
                    "за одинаковые периоды."
                ),
            ),
        ]

        result = summarize_dialogue(messages)

        self.assertIn(
            "сравнить потребление",
            result.discussed_solution,
        )

    def test_extract_open_question(self):
        messages = [
            Message(
                role="user",
                content="Хотим разобраться с расходами.",
            ),
            Message(
                role="assistant",
                content="Какая у вас ценовая категория?",
            ),
        ]

        result = summarize_dialogue(messages)

        self.assertEqual(
            result.open_questions,
            ["Какая у вас ценовая категория?"],
        )

    def test_empty_dialogue(self):
        result = summarize_dialogue([])

        self.assertEqual(result.problem, "")
        self.assertEqual(result.circumstances, "")
        self.assertEqual(result.discussed_solution, "")
        self.assertEqual(result.open_questions, [])

    def test_problem_with_phone_in_same_message(self):
        """Проблема сохраняется, телефон не попадает в резюме."""

        messages = [
            Message(
                role="user",
                content=(
                    "У нас выросли счета за электричество. "
                    "Мой телефон 89991234567."
                ),
            )
        ]

        result = summarize_dialogue(messages)

        self.assertIn(
            "выросли счета за электричество",
            result.problem,
        )

        self.assertNotIn(
            "89991234567",
            result.problem,
        )

    def test_contact_before_problem(self):
        """Проблема сохраняется, даже если сначала указан телефон."""

        messages = [
            Message(
                role="user",
                content=(
                    "Мой телефон 89991234567. "
                    "У нас выросли расходы на электроэнергию."
                ),
            )
        ]

        result = summarize_dialogue(messages)

        self.assertIn(
            "выросли расходы на электроэнергию",
            result.problem,
        )

        self.assertNotIn(
            "89991234567",
            result.problem,
        )

    def test_name_and_problem_in_one_sentence(self):
        """Проблема сохраняется после представления клиента."""

        messages = [
            Message(
                role="user",
                content=(
                    "Меня зовут Анна Иванова, "
                    "у нас выросли расходы на электроэнергию."
                ),
            )
        ]

        result = summarize_dialogue(messages)

        self.assertIn(
            "выросли расходы на электроэнергию",
            result.problem,
        )

        self.assertNotIn(
            "Анна Иванова",
            result.problem,
        )

    def test_answered_question_is_not_open(self):
        """Отвеченный вопрос не должен оставаться открытым."""

        messages = [
            Message(
                role="user",
                content="У нас выросли счета за электричество.",
            ),
            Message(
                role="assistant",
                content="Какая у вас ценовая категория?",
            ),
            Message(
                role="user",
                content="Четвёртая.",
            ),
        ]

        result = summarize_dialogue(messages)

        self.assertEqual(
            result.open_questions,
            [],
        )

        self.assertIn(
            "Четвёртая",
            result.circumstances,
        )

if __name__ == "__main__":
    unittest.main()
