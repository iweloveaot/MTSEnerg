
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

        # Не включаем предложения,
        # содержащие только контактные сведения.
        if is_contact_message(sentence):
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
        "телефон:",
        "номер телефона:",
        "компания:",
        "название компании:",
    )

    return normalized.startswith(contact_only_prefixes)

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

    for message in messages:
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
        else ""
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
