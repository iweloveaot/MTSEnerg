"""Command-line search in the organizer archive."""

import argparse
import csv
import json
from dataclasses import asdict

from .search import SearchIndex, parse_question


def main():
    parser = argparse.ArgumentParser(description="Поиск по архиву базы знаний EnergyTool.")
    parser.add_argument("archive", help="Путь к knowledge-base.zip")
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--question", help="Вопрос или диалог")
    query.add_argument("--questions", help="CSV с колонками id,question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    index = SearchIndex.from_zip(args.archive)
    if args.questions:
        with open(args.questions, encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    else:
        rows = [{"id": "local", "question": args.question}]
    for row in rows:
        hits = index.search(parse_question(row["question"]), top_k=args.top_k)
        sources = [{**asdict(hit.source), "score": round(hit.score, 3)} for hit in hits]
        print(json.dumps({"id": row["id"], "sources": sources}, ensure_ascii=False))


if __name__ == "__main__":
    main()
