
import json
import unittest

from application_agent import (
    ApplicationAgentInput,
    Contacts,
    Message,
    run_application_agent,
)

from application_agent.serializer import (
    result_to_dict,
    result_to_json,
)


class SerializerTests(unittest.TestCase):

    def test_result_to_dict(self):
        data = ApplicationAgentInput(
            session_id="test-json-1",
            messages=[
                Message(
                    role="user",
                    content=(
                        "У нас выросли счета "
                        "за электричество."
                    ),
                ),
            ],
            current_draft=Contacts(
                full_name="Анна Иванова",
                phone="8 (999) 123-45-67",
                company="Ромашка",
            ),
            application_requested=True,
        )

        result = run_application_agent(data)

        serialized = result_to_dict(result)

        self.assertEqual(
            serialized["contacts"]["full_name"],
            "Анна Иванова",
        )

        self.assertEqual(
            serialized["contacts"]["phone"],
            "+79991234567",
        )

        self.assertEqual(
            serialized["summary"]["problem"],
            "У нас выросли счета за электричество.",
        )

        self.assertTrue(serialized["ready"])

    def test_result_to_json(self):
        data = ApplicationAgentInput(
            session_id="test-json-2",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
                phone="89991234567",
                company="Ромашка",
            ),
            application_requested=True,
        )

        result = run_application_agent(data)

        json_string = result_to_json(result)

        parsed = json.loads(json_string)

        self.assertEqual(
            parsed["status"],
            "ready",
        )

        self.assertEqual(
            parsed["contacts"]["company"],
            "Ромашка",
        )

        self.assertEqual(
            parsed["missing_fields"],
            [],
        )

    def test_incomplete_application_json(self):
        data = ApplicationAgentInput(
            session_id="test-json-3",
            messages=[],
            current_draft=Contacts(
                full_name="Анна Иванова",
            ),
        )

        result = run_application_agent(data)

        parsed = json.loads(result_to_json(result))

        self.assertFalse(parsed["ready"])

        self.assertEqual(
            parsed["missing_fields"],
            ["phone", "company"],
        )

        self.assertIsNone(
            parsed["contacts"]["phone"]
        )


if __name__ == "__main__":
    unittest.main()
