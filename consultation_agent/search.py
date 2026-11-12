"""Rank knowledge-base sections for the active dialogue topic."""

import math
import re
from collections import Counter

from .knowledge_base import load_sources
from .models import Hit, Source


ROLE = re.compile(
    r"^[ \t]*(пользователь|клиент|user|ассистент|бот|консультант|assistant)[ \t]*:[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)
USER_ROLES = {"пользователь", "клиент", "user"}
TOPIC_SWITCH = re.compile(
    r"^\s*(?:давайте\s+)?(?:сменим тему|другой вопрос|новый вопрос)\b[.!?:,\s–—-]*",
    re.IGNORECASE,
)
TOPIC_RETURN = re.compile(
    r"^\s*(?:давайте\s+)?(?:верн[её]мся|возвращаясь)\s+к\s+",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-zа-я0-9]+")
STOP = set("""
а без был была были было бы вам вас ваш ваши ведь во вот вы где да даже для
до его ее если есть еще за из или им их к как какая какие какой когда кто ли
либо мне мы на надо нам нас наш не нет ни но ну о об он она они от по под
при про раз с со так там такой те тем то того тоже только тут ты у уже что
чтобы чем это этот я могу можно надо нужно нужны нужен хотим хочу сможете
сможет скажите подскажите пожалуйста вообще будет будут ваш вашей ваших
вашем ваша этом наши сейчас несколько примерно такой таких этих
квт мвт кwh квтч
""".split())
SUFFIX = re.compile(
    r"(?:иями|ями|ами|ого|его|ому|ему|ыми|ими|иях|ией|ью|иям|"
    r"ать|ять|ить|еть|ировать|аться|яться|иться|"
    r"ая|яя|ое|ее|ие|ые|ой|ей|ый|ий|ую|юю|ам|ям|ах|ях|ых|их|ов|ев|ом|ем|"
    r"ия|ию|ии|ья|ье|ьи|а|я|ы|и|у|ю|е|о|ь)$"
)
TERM_EQUIVALENTS = {
    "sim": "сим",
    "аскуэ": "платформ",
    "фот": "фото",
    "фотограф": "фото",
    "фотографи": "фото",
    "фотографий": "фото",
    "фотоснимок": "фото",
    "симка": "сим",
    "симк": "сим",
    "тарифн": "тариф",
    "двухтарифн": "тариф",
    "многотарифн": "тариф",
    "энергопотреблен": "потреблен",
    "электросчетчик": "счетчик",
    "крыш": "кровл",
    "фасад": "вертикальн",
    "выпуск": "производств",
    "вырос": "рост",
    "выросл": "рост",
    "растет": "рост",
    "раст": "рост",
    "сниз": "снижен",
    "расширен": "расшир",
    "расширятьс": "расшир",
    "автоматическ": "автомат",
    "автоматиз": "автомат",
    "автоматизац": "автомат",
    "автоматизированн": "автомат",
}
GENERIC_TERMS = {"год", "данн", "нач", "работ", "больш", "два", "три", "телефон"}
SEARCH_VERSION = "lexical-focus-v3"

ORDINAL_CATEGORY = re.compile(
    r"\b(?:перв|втор|трет|четверт|пят|шест)[а-я]+\b|\b[1-6](?:[-‑–]?[ая](?:я|й|ю)?)?\b"
)

def tokens(text: str) -> list[str]:
    text = text.casefold().replace("ё", "е")
    words = WORD.findall(text)
    result = []
    for word in words:
        if word in STOP or len(word) < 2:
            continue
        if word == "стоить":
            word = "стоимость"
        suffix = SUFFIX.search(word)
        if suffix and suffix.start() >= 3:
            word = word[:suffix.start()]
        result.append(TERM_EQUIVALENTS.get(word, word))
    return result

def parse_question(question: str) -> list[dict[str, str]]:
    """Convert an organizer CSV question or role-marked dialogue to messages."""
    matches = list(ROLE.finditer(question))
    if not matches or question[:matches[0].start()].strip():
        return [{"role": "user", "content": question.strip()}]
    messages = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(question)
        content = question[match.end():end].strip()
        if content:
            role = "user" if match[1].casefold() in USER_ROLES else "assistant"
            messages.append({"role": role, "content": content})
    return messages


def current_dialogue(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user" and messages[index]["content"].strip():
            return messages[:index + 1]
    raise ValueError("В диалоге нет непустой реплики пользователя.")


def search_dialogue(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    dialogue = current_dialogue(messages)
    for index in range(len(dialogue) - 1, -1, -1):
        message = dialogue[index]
        if message["role"] != "user":
            continue
        change = TOPIC_SWITCH.match(message["content"])
        resume = TOPIC_RETURN.match(message["content"])
        if not (change or resume):
            continue
        first = {**message, "content": message["content"][(change or resume).end():]}
        active = [first, *dialogue[index + 1:]]
        if resume:
            terms = set(tokens(first["content"])) - GENERIC_TERMS
            related = [
                earlier for earlier in dialogue[:index]
                if earlier["role"] == "user" and terms.intersection(tokens(earlier["content"]))
            ]
            return [*related[-3:], *active]
        return active
    return dialogue


def focus_queries(dialogue: list[dict[str, str]], turns: list[str]) -> list[str]:
    """Resolve a few product terms and references that lexical search tends to miss."""
    latest = set(tokens(turns[-1]))
    nearby = set(tokens(" ".join(turns[-3:])))
    previous = set(tokens(dialogue[-2]["content"])) if len(dialogue) > 1 else set()
    queries = []
    if {"рост", "счет"} <= latest:
        queries.append("рост счета за электроэнергию потребление плата за мощность")
    if "фото" in latest and {"прибор", "счетчик", "показан"} & nearby and (
        {"платформ", "обход", "вручн", "ручн"} & nearby
    ):
        queries.append(
            "распознавание показаний по фото платформу учета подключенными обходами ручной ввод"
        )
    if "категор" in (latest | previous) and (
        "ценов" in latest or ORDINAL_CATEGORY.search(turns[-1].casefold().replace("ё", "е"))
    ):
        queries.append("шесть ценовых категорий почасовая цена передача тариф планирование")
    if (
        {"оценк", "расчет", "смет"} & latest
        and any(term.startswith(("данн", "сведен", "понадоб", "потребу", "подготов", "собра", "точн"))
                for term in latest)
        and {"учет", "прибор", "счетчик"} & nearby
        and {"платформ", "автомат"} & nearby
        and not {"солнечн", "потер", "оптов"} & latest
    ):
        queries.append("какие сведения могут понадобиться для платформы учета схема сбора данных тип приборов количество")
    return queries


class SearchIndex:
    def __init__(self, sources: list[Source]):
        self.sources = tuple(sources)
        self._entries = []
        doc_freq = Counter()
        for source in self.sources:
            body = Counter(tokens(source.text))
            title = set(tokens(source.headings[-1]))
            parents = set(tokens(" ".join(source.headings[:-1]))) - title
            self._entries.append((body, title, parents, sum(body.values())))
            doc_freq.update(body.keys() | title | parents)
        size = len(self.sources)
        self._avg_length = (sum(entry[3] for entry in self._entries) / size or 1) if size else 1
        self._idf = {
            term: math.log1p((size - count + 0.5) / (count + 0.5))
            for term, count in doc_freq.items()
        }

    @classmethod
    def from_zip(cls, archive_path):
        return cls(load_sources(archive_path))

    def search(self, messages: list[dict[str, str]], *, top_k: int = 5) -> list[Hit]:
        if top_k < 1:
            raise ValueError("top_k должен быть положительным.")
        dialogue = search_dialogue(messages)
        turns = [msg["content"] for msg in dialogue if msg["role"] == "user"]
        weights = dict.fromkeys(tokens(turns[-1]), 1.0)
        for weight, turn in zip((0.75, 0.50, 0.25), reversed(turns[:-1])):
            for term in tokens(turn):
                weights.setdefault(term, weight)
        if len(dialogue) > 1 and dialogue[-2]["role"] == "assistant":
            for term in tokens(dialogue[-2]["content"]):
                weights.setdefault(term, 0.35)
        if not weights:
            return []
        scores = self._rank(weights)
        for query in focus_queries(dialogue, turns):
            focused = self._rank(dict.fromkeys(tokens(query), 1.0))
            if focused:
                source, score = max(focused.items(), key=lambda pair: (pair[1], pair[0].section_id))
                scores[source] = scores.get(source, 0.0) + score
        hits = [Hit(source, score) for source, score in scores.items()]
        hits.sort(key=lambda hit: (-hit.score, hit.source.section_id))
        return hits[:top_k]

    def _rank(self, weights: dict[str, float]) -> dict[Source, float]:
        scores = []
        doc_terms = {}
        for source, (body, title, parents, length) in zip(self.sources, self._entries):
            norm = 1.2 * (0.25 + 0.75 * length / self._avg_length)
            score = 0.0
            best = doc_terms.setdefault(source.document_id, {})
            for term, weight in weights.items():
                if term not in self._idf:
                    continue
                count = body[term]
                relevance = 2.2 * count / (count + norm)
                relevance += 1.35 * (term in title) + 0.30 * (term in parents)
                weighted = relevance * weight * self._idf[term]
                if term in GENERIC_TERMS:
                    weighted *= 0.35
                score += weighted
                if weighted > best.get(term, 0):
                    best[term] = weighted
            if score > 0:
                scores.append((source, score))
        document_scores = {doc_id: sum(terms.values()) for doc_id, terms in doc_terms.items()}
        return {
            source: score + 0.35 * document_scores[source.document_id]
            for source, score in scores
        }
