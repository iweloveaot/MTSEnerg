
import unittest

from application_agent.models import Message
from application_agent.summarizer import summarize_dialogue


class SummarizerTests(unittest.TestCase):

    def test_only_application_and_contacts_not_a_problem(self):
        messages = [
            Message(role="user", content="Хочу оформить заявку"),
            Message(role="assistant", content="Как я могу к вам обращаться? Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="Иван Петров"),
            Message(role="assistant", content="Если хотите оставить заявку специалисту, подскажите, пожалуйста, номер телефона для связи."),
            Message(role="user", content="89123333333"),
            Message(role="assistant", content="Подскажите, пожалуйста, название вашей компании."),
            Message(role="user", content="Компания ООО ТестЭнерго"),
            Message(role="assistant", content="Данные заявки собраны. Они отображаются в карточке заявки; отправка менеджеру пока не подключена."),
        ]
        result = summarize_dialogue(messages)
        self.assertEqual(result.problem, "Задача клиента пока не уточнена.")
        self.assertEqual(result.circumstances, "")
        self.assertEqual(result.discussed_solution, "")
        self.assertEqual(result.open_questions, [])

    def test_real_energy_problem_survives_application_and_contacts(self):
        messages = [
            Message(role="user", content="У нас выросли счета за электричество."),
            Message(role="assistant", content="Какая у вас ценовая категория?"),
            Message(role="user", content="Четвёртая."),
            Message(role="user", content="Хочу оформить заявку"),
            Message(role="assistant", content="Как я могу к вам обращаться? Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="Иван Петров"),
            Message(role="user", content="Компания ООО ТестЭнерго"),
            Message(role="user", content="89123333333"),
        ]
        result = summarize_dialogue(messages)
        self.assertEqual(result.problem, "У нас выросли счета за электричество.")
        self.assertIn("Четвёртая", result.circumstances)
        self.assertNotIn("Иван Петров", result.circumstances)
        self.assertNotIn("ТестЭнерго", result.circumstances)
        self.assertNotIn("89123333333", result.circumstances)

    def test_application_intent_followed_by_problem_in_same_message(self):
        result = summarize_dialogue([
            Message(role="user", content="Хочу оформить заявку, у нас выросли счета за электричество.")
        ])
        self.assertEqual(result.problem, "у нас выросли счета за электричество.")

    def test_contact_prompt_not_in_discussed_solution(self):
        result = summarize_dialogue([
            Message(role="user", content="Хотим снизить расходы."),
            Message(role="assistant", content="Подскажите, пожалуйста, название вашей компании."),
            Message(role="assistant", content="Предлагаю сравнить потребление за одинаковые периоды."),
        ])
        self.assertEqual(result.discussed_solution, "Предлагаю сравнить потребление за одинаковые периоды.")

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
