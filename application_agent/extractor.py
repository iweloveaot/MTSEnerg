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


def find_name(text: str) -> str | None:
    matches = list(NAME_PATTERN.finditer(text))

    if not matches:
        return None

    return matches[-1].group(1).strip()


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

    for message in messages:
        if message.role != "user":
            continue

        text = message.content.strip()

        if not text:
            continue

        if REFUSAL_PATTERN.search(text):
            declined = True

        name = find_name(text)
        company = find_company(text)
        phone = find_phone(text)

        if name is not None:
            contacts.full_name = name

        if company is not None:
            contacts.company = company

        if phone is not None:
            contacts.phone = phone
            declined = False

    return contacts, declined
