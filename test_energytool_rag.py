import csv
import io
import json
import os
import unittest
from pathlib import Path
from zipfile import ZipFile

from energytool_rag import SearchIndex, consult, parse_question


class ConsultationTests(unittest.TestCase):
    def setUp(self):
        archive = io.BytesIO()
        with ZipFile(archive, "w") as file:
            file.writestr("catalog/solar.md", (
                "# Солнечная станция\n\n"
                "## Размещение\n\n"
                "- Можно рассмотреть крышу.\n"
                "- Требуется оценка кровли.\n\n"
                "## Выработка\n\nВыработка зависит от региона.\n"
            ))
            file.writestr("catalog/metering.md", (
                "# Учёт\n\nПриборы передают показания.\n\n"
                "## Стоимость\n\nОриентир — 25 000 руб. за прибор в год.\n"
            ))
        archive.seek(0)
        self.index = SearchIndex.from_zip(archive)

    def test_source_contains_condition_and_heading_location(self):
        [hit] = self.index.search(parse_question("Можно установить на крыше?"), top_k=1)
        self.assertEqual(hit.source.section_id, "catalog/solar#02")
        self.assertEqual(hit.source.line, 3)
        self.assertEqual(hit.source.headings, ("Солнечная станция", "Размещение"))
        self.assertIn("- Требуется оценка кровли.", hit.source.text)

    def test_latest_user_message_and_prior_context(self):
        messages = parse_question(
            "Пользователь: Можно рассмотреть солнечную станцию?\n"
            "Ассистент: Какая у вас задача?\n"
            "Пользователь: А это подойдёт?\n"
            "Ассистент: Эта реплика следует после вопроса."
        )
        self.assertEqual(len(messages), 4)

        def generate(prompt):
            payload = json.loads(prompt[1]["content"])
            self.assertEqual(payload["dialogue"][-1]["content"], "А это подойдёт?")
            self.assertEqual(len(payload["dialogue"]), 3)
            source_id = payload["knowledge_base"][0]["id"]
            return json.dumps({
                "action": "answer", "answer": "Нужна оценка объекта.",
                "source_ids": [source_id],
            })

        result = consult(self.index, messages, generate)
        self.assertEqual(result.action, "answer")
        self.assertEqual(result.sources[0].document_id, "catalog/solar")

    def test_clarification_and_specialist(self):
        for action, answer in (
            ("clarify", "Что вы хотите улучшить в учёте?"),
            ("specialist", "Могу предложить консультацию специалиста."),
        ):
            with self.subTest(action=action):
                payload = json.dumps({"action": action, "answer": answer, "source_ids": []})
                result = consult(self.index, parse_question("Подскажите"), lambda _: payload)
                self.assertEqual((result.action, result.answer, result.sources), (action, answer, ()))

    def test_factual_response_requires_a_real_source(self):
        messages = parse_question("Можно установить на крыше?")
        for raw, expected_issue in (
            ("не JSON", "invalid_json"),
            (json.dumps({"action": "answer", "answer": "Да", "source_ids": []}),
             "invalid_response"),
            (json.dumps({"action": "answer", "answer": "Да", "source_ids": ["unknown#42"]}),
             "invalid_response"),
        ):
            with self.subTest(raw=raw):
                result = consult(self.index, messages, lambda _: raw)
                self.assertEqual((result.action, result.sources), ("specialist", ()))
                self.assertEqual(result.generation_issue, expected_issue)

    def test_ruble_amount_requires_support_from_the_cited_section(self):
        messages = parse_question("Какая стоимость учёта за прибор?")
        for price, source, expected_issue in (
            ("25 тыс. рублей", "catalog/metering#02", None),
            ("19 000 руб.", "catalog/metering#02", "unsupported_price"),
            ("25 000 рублей", "catalog/metering#01", "unsupported_price"),
        ):
            with self.subTest(price=price, source=source):
                answer = f"Ориентир — {price} за прибор в год."
                payload = json.dumps({"action": "answer", "answer": answer, "source_ids": [source]})
                result = consult(self.index, messages, lambda _: payload)
                self.assertEqual(result.generation_issue, expected_issue)
                self.assertEqual(result.action, "specialist" if expected_issue else "answer")


@unittest.skipUnless(os.getenv("ENERGYTOOL_QA_DATA"), "Укажите каталог ENERGYTOOL_QA_DATA.")
class CorpusRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = Path(os.environ["ENERGYTOOL_QA_DATA"])
        cls.index = SearchIndex.from_zip(data / "knowledge-base.zip")
        with (data / "demo_questions.csv").open(encoding="utf-8-sig", newline="") as file:
            cls.questions = {row["id"]: row["question"] for row in csv.DictReader(file)}

    def test_questions_with_known_retrieval_gaps(self):
        expected = {
            "10": {"10-energy/14-tariffs#02"},
            "15": {"20-products/25-meter-reading#03", "20-products/22-askue#03"},
            "17": {"10-energy/11-price-categories#04", "10-energy/14-tariffs#02"},
            "18": {"00-reference/03-calculation-and-requests#07"},
        }
        for case, sources in expected.items():
            with self.subTest(case=case):
                hits = self.index.search(parse_question(self.questions[case]))
                self.assertTrue(sources <= {hit.source.section_id for hit in hits})
                if case == "10":
                    self.assertIn(hits[0].source.section_id, sources)

    def test_follow_up_with_numeric_category_and_subject_change(self):
        history = (
            "Пользователь: У предприятия вырос счёт.\n"
            "Ассистент: Какая у вас ценовая категория?\n"
            "Пользователь: 4-я. Что проверить в платёжке?"
        )
        hits = self.index.search(parse_question(history))
        self.assertIn("10-energy/11-price-categories#04", {hit.source.section_id for hit in hits})

        question = "Можно поставить солнечные панели на фасад?"
        switched = history + "\nПользователь: Сменим тему. " + question
        fresh = self.index.search(parse_question(question))
        self.assertEqual(self.index.search(parse_question(switched)), fresh)
        self.assertIn("20-products/23-solar#10", {hit.source.section_id for hit in fresh})


if __name__ == "__main__":
    unittest.main()
