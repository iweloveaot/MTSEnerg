import unittest

from application_agent import (
    ApplicationAgentInput,
    Contacts,
    Message,
    run_application_agent,
)


class ApplicationAgentTests(
    unittest.TestCase
):

    def test_missing_phone(self):
        data = ApplicationAgentInput(
            session_id="test-1",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
                company="Ромашка",
            ),
            application_requested=True,
        )

        result = run_application_agent(
            data
        )

        self.assertFalse(
            result.ready
        )

        self.assertEqual(
            result.status,
            "draft",
        )

        self.assertEqual(
            result.missing_fields,
            ["phone"],
        )

        self.assertIsNotNone(
            result.next_question
        )

    def test_complete_application(self):
        data = ApplicationAgentInput(
            session_id="test-2",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
                phone="8 (999) 123-45-67",
                company="Ромашка",
            ),
            application_requested=True,
        )

        result = run_application_agent(
            data
        )

        self.assertTrue(
            result.ready
        )

        self.assertEqual(
            result.status,
            "ready",
        )

        self.assertEqual(
            result.missing_fields,
            [],
        )

        self.assertIsNone(
            result.next_question
        )

        self.assertEqual(
            result.contacts.phone,
            "+79991234567",
        )

    def test_invalid_phone(self):
        data = ApplicationAgentInput(
            session_id="test-3",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
                phone="12345",
                company="Ромашка",
            ),
        )

        result = run_application_agent(
            data
        )

        self.assertFalse(
            result.ready
        )

        self.assertIn(
            "phone",
            result.missing_fields,
        )

        self.assertIsNone(
            result.contacts.phone
        )

    def test_contact_refusal(self):
        data = ApplicationAgentInput(
            session_id="test-4",
            messages=[],
            current_draft=Contacts(),
            contact_collection_declined=True,
        )

        result = run_application_agent(
            data
        )

        self.assertFalse(
            result.ready
        )

        self.assertEqual(
            result.status,
            "declined",
        )

        self.assertIsNone(
            result.next_question
        )

    def test_agent_creates_summary(self):
        data = ApplicationAgentInput(
            session_id="test-summary",
            messages=[
                Message(
                    role="user",
                    content="У нас выросли счета за электричество.",
                ),
                Message(
                    role="assistant",
                    content="Какая у вас ценовая категория?",
                ),
            ],
            current_draft=Contacts(),
        )

        result = run_application_agent(data)

        self.assertEqual(
            result.summary.problem,
            "У нас выросли счета за электричество.",
        )

        self.assertIn(
            "Какая у вас ценовая категория?",
            result.summary.open_questions,
        )

    def test_complete_contacts_without_consent(self):
        """Контакты известны, но клиент не просил оформить заявку."""

        data = ApplicationAgentInput(
            session_id="test-without-consent",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
                phone="8 (999) 123-45-67",
                company="Ромашка",
            ),
            application_requested=False,
        )

        result = run_application_agent(data)

        self.assertFalse(result.ready)
        self.assertIsNone(result.next_question)
        self.assertEqual(result.status, "draft")
        self.assertEqual(result.missing_fields, [])

    def test_refusal_after_application_request(self):
        """После отказа агент прекращает сбор контактов."""

        data = ApplicationAgentInput(
            session_id="test-refusal-after-consent",
            messages=[
                Message(
                    role="user",
                    content="Я пока не готов оставлять телефон.",
                ),
            ],
            current_draft=Contacts(
                full_name="Анна Иванова",
                company="Ромашка",
            ),
            application_requested=True,
        )

        result = run_application_agent(data)

        self.assertFalse(result.ready)
        self.assertTrue(result.contact_collection_declined)
        self.assertEqual(result.status, "declined")
        self.assertIsNone(result.next_question)
        self.assertIn("phone", result.missing_fields)

if __name__ == "__main__":
    unittest.main()