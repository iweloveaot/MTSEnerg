import re

from .models import Contacts, Message
from .validator import normalize_phone


NAME_PATTERN = re.compile(
    r"(?:меня\s+зовут|мо[её]\s+имя)"
    r"\s*[:—-]?\s*"
    r"([А-ЯЁ][а-яё-]+"
    r"(?:\s+[А-ЯЁ][а-яё-]+){1,2})",
    re.IGNORECASE,
)

COMPANY_PATTERN = re.compile(
    r"\b(?:компания|компании|организация|организации)"
    r"\s+(?:ООО\s+)?"
    r"([«\"][^»\"]+[»\"]|"
    r"[А-ЯЁа-яёA-Za-z][\w-]*"
    r"(?:\s+(?!(?:телефон|номер|меня|мой|моя|и)\b)"
    r"[А-ЯЁа-яёA-Za-z][\w-]*){0,2})",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+7|8|7|9)"
    r"(?:[\s()\-]*\d){9,10}(?!\d)"
)

PHONE_CONTEXT = re.compile(
    r"(?:телефон|номер|для\s+связи|позвонить)",
    re.IGNORECASE,
)

REFUSAL_PATTERN = re.compile(
    r"(?:не\s+готов\w*|не\s+хочу|не\s+буду)"
    r".{0,50}(?:телефон|номер|контакт)"
    r"|(?:телефон|номер).{0,30}"
    r"(?:не\s+дам|не\s+оставлю)",
    re.IGNORECASE,
)


# A short name-only answer is accepted only in response to the assistant's
# explicit request for a name. This avoids treating product names as contacts.
STANDALONE_NAME_PATTERN = re.compile(
    r"[А-ЯЁа-яё][а-яё-]+(?:\s+[А-ЯЁа-яё][а-яё-]+){1,2}[.!]?",
    re.IGNORECASE,
)
NAME_QUESTION_PATTERN = re.compile(
    r"как\s+я\s+могу\s+к\s+вам\s+обращаться|имя\s+и\s+фамилию",
    re.IGNORECASE,
)


# Ответ без слова «компания» допустим только после вопроса о компании.
COMPANY_QUESTION_PATTERN = re.compile(
    r"(?:название|назовите)\s+(?:вашей\s+)?компании|"
    r"как\s+называется\s+(?:ваша\s+)?компания",
    re.IGNORECASE,
)
COMPANY_ANSWER_PATTERN = re.compile(
    r"(?:(?:ООО|АО|ПАО|ИП)\s+)?[А-ЯЁа-яёA-Za-z][\w-]*"
    r"(?:\s+[А-ЯЁа-яёA-Za-z][\w-]*){0,3}"
)
COMPANY_STOP_ANSWERS = {"не знаю", "нет компании", "нет", "пока нет", "не хочу", "без компании"}


def find_company_answer(text: str) -> str | None:
    candidate = text.strip().strip(' «»".!')
    if not candidate or candidate.casefold() in COMPANY_STOP_ANSWERS:
        return None
    if not COMPANY_ANSWER_PATTERN.fullmatch(candidate):
        return None
    if NAME_PATTERN.search(candidate) or PHONE_PATTERN.search(candidate):
        return None
    return candidate.removeprefix("ООО ").strip() if candidate.startswith("ООО ") else candidate


def find_name(text: str, *, asked_for_name: bool = False) -> str | None:
    matches = list(NAME_PATTERN.finditer(text))
    if matches:
        return matches[-1].group(1).strip()

    candidate = text.strip().rstrip(".!")
    if (asked_for_name
            and STANDALONE_NAME_PATTERN.fullmatch(text.strip())
            and not COMPANY_PATTERN.search(candidate)
            and not candidate.casefold().startswith(("компания ", "организация "))):
        return " ".join(part[:1].upper() + part[1:].lower()
                        for part in candidate.split())

    return None


def find_company(text: str) -> str | None:
    matches = list(COMPANY_PATTERN.finditer(text))

    if not matches:
        return None

    value = matches[-1].group(1)

    return value.strip(' «»"')


def find_phone(text: str) -> str | None:
    for match in reversed(list(PHONE_PATTERN.finditer(text))):
        candidate = match.group()

        # Не считаем любое длинное число телефоном:
        # это может быть потребление электроэнергии.
        context = text[max(0, match.start() - 50):match.start()]

        has_phone_context = PHONE_CONTEXT.search(context)
        is_standalone = text.strip() == candidate.strip()
        has_country_prefix = candidate.startswith("+7")

        if not (
            has_phone_context
            or is_standalone
            or has_country_prefix
        ):
            continue

        phone = normalize_phone(candidate)

        if phone is not None:
            return phone

    return None


def extract_contacts(
    messages: list[Message],
    current_draft: Contacts,
    contact_collection_declined: bool = False,
) -> tuple[Contacts, bool]:
    """
    Извлекает контакты из сообщений пользователя.

    Сообщения обрабатываются по порядку:
    более новые явно указанные данные
    заменяют старые.

    Ответы ассистента игнорируются.
    """

    contacts = Contacts(
        full_name=current_draft.full_name,
        phone=current_draft.phone,
        company=current_draft.company,
    )

    declined = contact_collection_declined
    previous_message = None

    for message in messages:
        if message.role != "user":
            previous_message = message
            continue

        text = message.content.strip()

        if not text:
            previous_message = message
            continue

        if REFUSAL_PATTERN.search(text):
            declined = True

        asked_for_name = (
            previous_message is not None
            and previous_message.role == "assistant"
            and bool(NAME_QUESTION_PATTERN.search(previous_message.content))
        )
        name = find_name(text, asked_for_name=asked_for_name)
        company = find_company(text)
        asked_for_company = (
            previous_message is not None
            and previous_message.role == "assistant"
            and bool(COMPANY_QUESTION_PATTERN.search(previous_message.content))
        )
        if company is None and asked_for_company:
            company = find_company_answer(text)
        phone = find_phone(text)

        if name is not None:
            contacts.full_name = name

        if company is not None:
            contacts.company = company

        if phone is not None:
            contacts.phone = phone
            declined = False

        previous_message = message

    return contacts, declined
