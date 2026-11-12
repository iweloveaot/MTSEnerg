
import unittest

from application_agent import (
    ApplicationAgentInput,
    Contacts,
    Message,
    run_application_agent,
)


def make_result(
    messages,
    current_draft=None,
    application_requested=False,
):
    return run_application_agent(
        ApplicationAgentInput(
            session_id="test-extractor",
            messages=messages,
            current_draft=current_draft or Contacts(),
            application_requested=application_requested,
        )
    )

class ExtractorTests(unittest.TestCase):

    def test_extract_all_contacts(self):
        result = make_result(
            [
                Message(
                    role="user",
                    content=(
                        "Меня зовут Анна Иванова. "
                        "Компания Ромашка. "
                        "Телефон: 8 (999) 123-45-67."
                    ),
                )
            ],
            application_requested=True,
        )

        self.assertEqual(
            result.contacts.full_name,
            "Анна Иванова",
        )
        self.assertEqual(
            result.contacts.company,
            "Ромашка",
        )
        self.assertEqual(
            result.contacts.phone,
            "+79991234567",
        )
        self.assertTrue(result.ready)

    def test_standalone_name_after_name_question(self):
        result = make_result([
            Message(role="user", content="Хочу оформить заявку"),
            Message(role="assistant", content=(
                "Как я могу к вам обращаться? "
                "Укажите, пожалуйста, имя и фамилию."
            )),
            Message(role="user", content="Иван Петров"),
            Message(role="assistant", content="Подскажите телефон для связи."),
            Message(role="user", content="Компания ООО ТестЭнерго"),
        ], application_requested=True)
        self.assertEqual(result.contacts.full_name, "Иван Петров")
        self.assertEqual(result.contacts.company, "ТестЭнерго")
        self.assertEqual(result.missing_fields, ["phone"])
        self.assertIn("телефон", result.next_question)

    def test_lowercase_name_after_name_question(self):
        result = make_result([
            Message(role="assistant", content="Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="никита иванов"),
        ], application_requested=True)
        self.assertEqual(result.contacts.full_name, "Никита Иванов")
        self.assertIn("phone", result.missing_fields)

    def test_uppercase_name_after_name_question(self):
        result = make_result([
            Message(role="assistant", content="Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="НИКИТА ИВАНОВ"),
        ], application_requested=True)
        self.assertEqual(result.contacts.full_name, "Никита Иванов")

    def test_lowercase_name_not_guessed_without_question(self):
        result = make_result([Message(role="user", content="никита иванов")])
        self.assertIsNone(result.contacts.full_name)

    def test_company_prefix_not_mistaken_for_name(self):
        result = make_result([
            Message(role="assistant", content="Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="компания ромашка"),
        ])
        self.assertIsNone(result.contacts.full_name)

    def test_unprompted_standalone_name_not_guessed(self):
        result = make_result([
            Message(role="user", content="Иван Петров"),
        ])
        self.assertIsNone(result.contacts.full_name)

    def test_standalone_name_does_not_capture_company(self):
        result = make_result([
            Message(role="assistant", content="Укажите, пожалуйста, имя и фамилию."),
            Message(role="user", content="Компания ООО ТестЭнерго"),
        ])
        self.assertIsNone(result.contacts.full_name)
        self.assertEqual(result.contacts.company, "ТестЭнерго")

    def test_company_name_without_prefix_after_question(self):
        result = make_result([
            Message(role="user", content="Оформить заявку"),
            Message(role="assistant", content="Подскажите, пожалуйста, название вашей компании."),
            Message(role="user", content="Сеньор"),
        ], application_requested=True)
        self.assertEqual(result.contacts.company, "Сеньор")

    def test_unprompted_company_name_not_guessed(self):
        result = make_result([Message(role="user", content="Сеньор")])
        self.assertIsNone(result.contacts.company)

    def test_company_name_replaced_after_new_company_question(self):
        result = make_result([
            Message(role="assistant", content="Подскажите название вашей компании."),
            Message(role="user", content="Ромашка"),
            Message(role="assistant", content="Подскажите название вашей компании."),
            Message(role="user", content="Сеньор"),
        ])
        self.assertEqual(result.contacts.company, "Сеньор")

    def test_corrected_phone(self):
        result = make_result([
            Message(
                role="user",
                content="Мой телефон 8 (999) 123-45-67",
            ),
            Message(
                role="user",
                content=(
                    "Нет, мой номер другой: "
                    "8 (999) 555-44-33"
                ),
            ),
        ])

        self.assertEqual(
            result.contacts.phone,
            "+79995554433",
        )

    def test_corrected_name(self):
        result = make_result([
            Message(
                role="user",
                content="Меня зовут Анна Иванова",
            ),
            Message(
                role="user",
                content=(
                    "Исправление: меня зовут Мария Петрова"
                ),
            ),
        ])

        self.assertEqual(
            result.contacts.full_name,
            "Мария Петрова",
        )

    def test_assistant_messages_are_ignored(self):
        result = make_result([
            Message(
                role="assistant",
                content=(
                    "Меня зовут Анна Иванова. "
                    "Компания Ромашка. "
                    "Телефон +79991234567"
                ),
            )
        ])

        self.assertIsNone(result.contacts.full_name)
        self.assertIsNone(result.contacts.company)
        self.assertIsNone(result.contacts.phone)

    def test_refusal_without_phone(self):
        result = make_result([
            Message(
                role="user",
                content=(
                    "Я пока не готов оставлять телефон. "
                    "Можете объяснить, что нужно для оценки?"
                ),
            )
        ])

        self.assertEqual(result.status, "declined")
        self.assertIsNone(result.next_question)
        self.assertIsNone(result.contacts.phone)

    def test_no_invented_contacts(self):
        result = make_result([
            Message(
                role="user",
                content=(
                    "У нас три склада и сорок счётчиков. "
                    "Хотим автоматизировать учёт."
                ),
            )
        ])

        self.assertIsNone(result.contacts.full_name)
        self.assertIsNone(result.contacts.phone)
        self.assertIsNone(result.contacts.company)
        self.assertFalse(result.ready)


if __name__ == "__main__":
    unittest.main()
