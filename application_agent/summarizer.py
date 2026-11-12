
import re

from .models import ApplicationSummary, Message


# Фразы, относящиеся к сбору контактов,
# а не к энергетической задаче клиента.
CONTACT_WORDS = (
    "меня зовут",
    "моё имя",
    "мое имя",
    "мой телефон",
    "мой номер",
    "оставлять телефон",
    "оставить телефон",
    "ваш телефон",
    "номер телефона",
    "название вашей компании",
    "как я могу к вам обращаться",
)

# Для защиты от случайного включения
# телефонных номеров в резюме.
# Служебные реплики про заявку и вопросы сбора контактов не
# описывают энергетическую задачу клиента.
APPLICATION_INTENT = re.compile(
    r"^\s*(?:хочу\s+)?(?:оформить|оставить)\s+заявку"
    r"|^\s*оформите\s+заявку",
    re.IGNORECASE,
)
NAME_PROMPT = re.compile(
    r"как\s+я\s+могу\s+к\s+вам\s+обращаться|имя\s+и\s+фамилию",
    re.IGNORECASE,
)
CONTACT_PROMPT = re.compile(
    r"подскажите.{0,80}(?:номер\s+телефона|название\s+вашей\s+компании)"
    r"|номер\s+телефона\s+для\s+связи",
    re.IGNORECASE,
)
COMPANY_PROMPT = re.compile(
    r"название\s+(?:вашей\s+)?компании|как\s+называется\s+(?:ваша\s+)?компания",
    re.IGNORECASE,
)
PHONE_PROMPT = re.compile(r"номер\s+телефона|телефон\s+для\s+связи", re.IGNORECASE)
PHONE_CORRECTION = re.compile(
    r"^(?:исправьте|измените|замените|уточняю|нет[, ]+)?"
    r".{0,35}(?:мой\s+)?(?:телефон|номер)\b",
    re.IGNORECASE,
)
STANDALONE_COMPANY = re.compile(
    r"(?:(?:ООО|АО|ПАО|ИП)\s+)?[А-ЯЁа-яёA-Za-z][\w-]*"
    r"(?:\s+[А-ЯЁа-яёA-Za-z][\w-]*){0,3}"
)
APPLICATION_CONFIRMATION = re.compile(
    r"^\s*данные\s+заявки\s+собраны\b",
    re.IGNORECASE,
)
STANDALONE_NAME = re.compile(
    r"[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+){1,2}[.!]?"
)
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+7|8|7)"
    r"(?:[\s()\-]*\d){10}(?!\d)"
)

def clean_text(text: str) -> str:
    """
    Очищает сообщение для резюме.

    Удаляет отдельные контактные предложения
    и представление клиента в начале предложения,
    сохраняя описание его задачи.
    """

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text.strip(),
    )

    cleaned_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        # Убираем представление клиента,
        # если после ФИО продолжается описание задачи.
        sentence = re.sub(
            r"^(?:меня зовут|мо[её] имя)\s+"
            r"[А-ЯЁ][а-яё-]+"
            r"(?:\s+[А-ЯЁ][а-яё-]+){1,2}"
            r"\s*[,;:—-]?\s*",
            "",
            sentence,
            flags=re.IGNORECASE,
        ).strip()

        if not sentence:
            continue

        # Убираем намерение оформить заявку, сохраняя задачу,
        # если она сформулирована после запятой.
        sentence = re.sub(
            r"^(?:хочу\s+)?(?:оформить|оставить)\s+заявку\s*[,;:—-]\s*",
            "",
            sentence,
            flags=re.IGNORECASE,
        ).strip()
        if not sentence:
            continue

        # Не включаем предложения, содержащие только контакты
        # или само намерение оформить заявку.
        if (is_contact_message(sentence)
                or PHONE_CORRECTION.search(sentence)
                or APPLICATION_INTENT.fullmatch(sentence.rstrip(".! "))):
            continue

        # Скрываем телефон, если он остался
        # внутри содержательного предложения.
        sentence = PHONE_PATTERN.sub(
            "[телефон скрыт]",
            sentence,
        )

        cleaned_sentences.append(sentence)

    return " ".join(cleaned_sentences)


def is_contact_message(text: str) -> bool:
    """
    Проверяет, состоит ли сообщение только
    из контактной информации.

    Если в сообщении есть описание проблемы,
    не исключаем его целиком.
    """

    normalized = text.lower().strip()

    contact_only_prefixes = (
        "меня зовут",
        "моё имя",
        "мое имя",
        "мой телефон",
        "мой номер",
        "исправьте мой телефон",
        "исправьте телефон",
        "измените мой телефон",
        "замените телефон",
        "телефон:",
        "номер телефона:",
        "компания:",
        "компания ",
        "название компании:",
        "название компании ",
    )

    return (
        normalized.startswith(contact_only_prefixes)
        or bool(PHONE_PATTERN.fullmatch(text.strip()))
    )

def summarize_dialogue(
    messages: list[Message],
) -> ApplicationSummary:
    """
    Создаёт простое извлекающее резюме.

    Использует только сведения
    из переданной переписки.

    Ничего не запрашивает у LLM
    и не добавляет внешние факты.
    """

    user_statements = []
    assistant_explanations = []
    open_questions = []
    pending_question = None
    awaiting_contact = None

    for message in messages:
        # Короткое ФИО без слов «меня зовут» — ответ на запрос
        # контактов, а не обстоятельство обращения.
        if message.role == "assistant":
            if NAME_PROMPT.search(message.content):
                awaiting_contact = "name"
            elif COMPANY_PROMPT.search(message.content):
                awaiting_contact = "company"
            elif PHONE_PROMPT.search(message.content):
                awaiting_contact = "phone"
            else:
                awaiting_contact = None
            if (CONTACT_PROMPT.search(message.content)
                    or NAME_PROMPT.search(message.content)
                    or APPLICATION_CONFIRMATION.search(message.content)):
                continue
        elif message.role == "user":
            candidate = message.content.strip().strip(" .!«»")
            if awaiting_contact == "name" and (
                    STANDALONE_NAME.fullmatch(message.content.strip())
                    or re.fullmatch(r"[А-ЯЁа-яё-]+(?:\s+[А-ЯЁа-яё-]+){1,2}", candidate)):
                awaiting_contact = None
                continue
            if awaiting_contact == "company" and STANDALONE_COMPANY.fullmatch(candidate):
                awaiting_contact = None
                continue
            awaiting_contact = None

        text = clean_text(message.content)

        if not text:
            continue

        if is_contact_message(text):
            continue

        if message.role == "user":
            user_statements.append(text)

            # Если после уточняющего вопроса клиент ответил,
            # считаем этот вопрос закрытым.
            if pending_question is not None:
                pending_question = None

        elif message.role == "assistant":
            if text.endswith("?"):
                # Запоминаем последний заданный вопрос.
                pending_question = text
            else:
                assistant_explanations.append(text)

    # Пока используем простое правило:
    # первое содержательное сообщение клиента
    # считаем описанием задачи.
    problem = (
        user_statements[0]
        if user_statements
        else ("Задача клиента пока не уточнена." if messages else "")
    )

    # Последующие сообщения клиента
    # содержат уточнения и обстоятельства.
    circumstances = " ".join(
        user_statements[1:4]
    )

    # Важно: это слова консультанта,
    # а не подтверждённые факты о продукте.
    discussed_solution = " ".join(
        assistant_explanations[:2]
    )

    # Для менеджера оставляем
    # не более трёх вопросов.
    open_questions = (
        [pending_question]
        if pending_question is not None
        else []
    )

    return ApplicationSummary(
        problem=problem,
        circumstances=circumstances,
        discussed_solution=discussed_solution,
        open_questions=open_questions,
    )
