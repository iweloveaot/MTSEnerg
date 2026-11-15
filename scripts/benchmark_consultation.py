"""Compare lexical search, character TF-IDF and reciprocal rank fusion locally."""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from math import log, log1p, sqrt
from pathlib import Path
from time import perf_counter_ns

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from consultation_agent import SearchIndex, parse_question, search_dialogue


def trigrams(text):
    normalized = " ".join(re.findall(r"[а-яa-z0-9]+", text.casefold().replace("ё", "е")))
    if not normalized:
        return Counter()
    padded = f"  {normalized}  "
    return Counter(padded[i:i + 3] for i in range(len(padded) - 2))


class CharacterVectors:
    def __init__(self, sources):
        counts = [trigrams(" ".join((*source.headings, source.text))) for source in sources]
        frequencies = Counter(term for document in counts for term in document)
        self.idf = {term: 1 + log1p(len(sources) / frequency)
                    for term, frequency in frequencies.items()}
        self.documents = [
            (source.section_id, self.vector(count)) for source, count in zip(sources, counts)
        ]

    def vector(self, counts):
        weighted = {term: (1 + log(count)) * self.idf[term]
                    for term, count in counts.items() if term in self.idf}
        norm = sqrt(sum(value * value for value in weighted.values())) or 1
        return {term: value / norm for term, value in weighted.items()}

    def search(self, messages, top_k):
        dialogue = search_dialogue(messages)
        turns = [message["content"] for message in dialogue if message["role"] == "user"]
        context = " ".join(turns[-3:-1])
        if len(dialogue) >= 2 and dialogue[-2]["role"] == "assistant":
            context += " " + dialogue[-2]["content"]
        vectors = [self.vector(trigrams(text)) for text in (turns[-1], context)]
        scores = []
        for source_id, document in self.documents:
            score = sum(
                weight * sum(value * document.get(term, 0.0) for term, value in query.items())
                for weight, query in zip((1.0, 0.5), vectors)
            )
            if score > 0:
                scores.append((source_id, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        return [source_id for source_id, _ in scores[:top_k]]


def fuse(lexical, vector):
    scores = Counter()
    for ranking in (lexical, vector):
        for rank, source_id in enumerate(ranking, 1):
            scores[source_id] += 1 / (60 + rank)
    return sorted(scores, key=lambda source_id: (-scores[source_id], source_id))


def benchmark(index, vectors, cases, repeats=11):
    rows = []
    for case in cases:
        expected = set(case["used_source_ids"])
        if not expected:
            continue
        messages = parse_question(case["question"])
        latencies = {"lexical": [], "vector": [], "hybrid": []}
        for _ in range(repeats):
            started = perf_counter_ns()
            lexical = [hit.source.section_id for hit in index.search(messages, top_k=15)]
            ended_lexical = perf_counter_ns()
            vector = vectors.search(messages, 15)
            ended_vector = perf_counter_ns()
            hybrid = fuse(lexical, vector)
            ended_hybrid = perf_counter_ns()
            latencies["lexical"].append(ended_lexical - started)
            latencies["vector"].append(ended_vector - ended_lexical)
            latencies["hybrid"].append(ended_hybrid - started)
        rows.append({
            "id": case["id"],
            "expected": sorted(expected),
            "rankings": {"lexical": lexical, "vector": vector, "hybrid": hybrid},
            "median_ms": {name: statistics.median(values) / 1_000_000
                          for name, values in latencies.items()},
        })
    return rows


def summarize(rows):
    totals = {}
    for method in ("lexical", "vector", "hybrid"):
        totals[method] = {
            f"@{limit}": {
                "any": sum(bool(set(row["expected"]) & set(row["rankings"][method][:limit]))
                           for row in rows),
                "all": sum(set(row["expected"]) <= set(row["rankings"][method][:limit])
                           for row in rows),
            } for limit in (1, 3, 4, 5)
        }
        totals[method]["median_ms"] = round(statistics.median(
            row["median_ms"][method] for row in rows
        ), 3)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("cases", type=Path, help="JSONL с полями id, group, question, used_source_ids")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--group", choices=("demo", "holdout"), action="append")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line]
    started = perf_counter_ns()
    index = SearchIndex.from_zip(args.archive)
    lexical_build_ms = (perf_counter_ns() - started) / 1_000_000
    started = perf_counter_ns()
    vectors = CharacterVectors(index.sources)
    vector_build_ms = (perf_counter_ns() - started) / 1_000_000
    groups = {}
    for group in args.group or ("demo", "holdout"):
        rows = benchmark(index, vectors, [case for case in cases if case["group"] == group])
        if not rows:
            parser.error(f"В группе {group} нет примеров с отмеченными источниками.")
        groups[group] = {"count": len(rows), "totals": summarize(rows), "cases": rows}
    measurements = {"lexical_build_ms": lexical_build_ms, "vector_build_ms": vector_build_ms}
    summary = {group: {"count": data["count"], "totals": data["totals"]}
               for group, data in groups.items()}
    print(json.dumps({**measurements, **summary}, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps({**measurements, **groups}, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")


if __name__ == "__main__":
    main()
