"""Competition entry point: python solution.py (DATA_DIR -> submission.csv)."""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

from energytool_rag import SearchIndex, parse_question
from submission_model import ModelAdapter, Settings
from orchestration import process_message


def data_directory(data_dir=None):
    """Explicit setting wins; otherwise try data/, then the local project."""
    configured = data_dir or os.getenv("DATA_DIR")
    if configured:
        return Path(configured)
    candidates = [Path("data"), Path(__file__).resolve().parent]
    return next((path for path in candidates if (path / "questions.csv").is_file()), candidates[0])


def knowledge_path(data_dir=None):
    if os.getenv("KNOWLEDGE_BASE_PATH"):
        return Path(os.environ["KNOWLEDGE_BASE_PATH"])
    candidate = data_directory(data_dir) / "knowledge-base.zip"
    return candidate if candidate.exists() else Path(__file__).resolve().parent / "knowledge-base.zip"


def solve(message, history=None):
    """One independent question, without persistent web histories."""
    model = ModelAdapter(Settings.from_env())
    try:
        return process_message(message, model=model, history=history,
                               index=SearchIndex.from_zip(knowledge_path()))
    finally:
        model.close()


def run_batch(data_dir=None, output="submission.csv", *, model=None):
    directory = data_directory(data_dir)
    questions = directory / "questions.csv"
    if not questions.is_file():
        raise FileNotFoundError(
            f"Не найден файл вопросов: {questions.resolve()}. "
            "Поместите questions.csv в папку data рядом с местом запуска "
            "или задайте --data-dir ПУТЬ / переменную DATA_DIR."
        )
    with questions.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"id", "question"} <= set(reader.fieldnames or []):
            raise ValueError("questions.csv должен содержать колонки id,question")
        rows = list(reader)
    ids = [row["id"] for row in rows]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("ID вопросов должны быть непустыми и уникальными")
    index = SearchIndex.from_zip(knowledge_path(directory))
    own_model = model is None
    model = model if model is not None else ModelAdapter(Settings.from_env())
    answers = []
    try:
        for number, row in enumerate(rows, 1):
            print(f"[{number}/{len(rows)}] Обработка вопроса id={row['id']}", file=sys.stderr, flush=True)
            messages = parse_question(row["question"])
            if not messages or messages[-1]["role"] != "user":
                raise ValueError("Вопрос должен завершаться репликой пользователя: " + row["id"])
            try:
                result = process_message(messages[-1]["content"], history=messages[:-1],
                                         model=model, index=index)
            except Exception as exc:
                raise RuntimeError(f"Не удалось обработать вопрос id={row['id']}: {exc}") from exc
            answer = result["answer"]
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 10000:
                raise ValueError("Некорректный ответ для ID " + row["id"])
            answers.append({"id": row["id"], "answer": answer})
    finally:
        if own_model:
            model.close()
    destination = Path(output)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["id", "answer"])
            writer.writeheader()
            writer.writerows(answers)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(answers)


def main():
    parser = argparse.ArgumentParser(description="МТС Energytool: сабмит или локальная проверка")
    parser.add_argument("message", nargs="?")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--output", default="submission.csv")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.serve:
        import uvicorn
        uvicorn.run("backend.app:create_app", factory=True, host=args.host, port=args.port)
    elif args.message is not None:
        print(json.dumps(solve(args.message), ensure_ascii=False, indent=2))
    else:
        print(f"Сохранено ответов: {run_batch(args.data_dir, args.output)}; файл: {args.output}")


if __name__ == "__main__":
    main()
