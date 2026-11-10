from .extractor import extract_contacts
from .models import (
    ApplicationAgentInput,
    ApplicationAgentResult,
    ApplicationSummary,
    Contacts,
)
from .validator import normalize_phone
from .summarizer import summarize_dialogue

REQUIRED_FIELDS = (
    "full_name",
    "phone",
    "company",
)


QUESTIONS = {
    "full_name": (
        "Как я могу к вам обращаться? "
        "Укажите, пожалуйста, имя и фамилию."
    ),
    "phone": (
        "Если хотите оставить заявку специалисту, "
        "подскажите, пожалуйста, номер телефона для связи."
    ),
    "company": (
        "Подскажите, пожалуйста, название вашей компании."
    ),
}


def prepare_contacts(contacts: Contacts) -> Contacts:
    return Contacts(
        full_name=contacts.full_name.strip()
        if contacts.full_name
        else None,
        phone=normalize_phone(contacts.phone),
        company=contacts.company.strip()
        if contacts.company
        else None,
    )


def get_missing_fields(contacts: Contacts) -> list[str]:
    missing_fields = []

    for field_name in REQUIRED_FIELDS:
        value = getattr(contacts, field_name)

        if value is None or not str(value).strip():
            missing_fields.append(field_name)

    return missing_fields


def get_next_question(
    missing_fields: list[str],
    contact_collection_declined: bool,
    application_requested: bool,
) -> str | None:
    """Возвращает вопрос только при согласии на заявку."""

    if not application_requested:
        return None

    if contact_collection_declined:
        return None

    if not missing_fields:
        return None

    return QUESTIONS[missing_fields[0]]


def get_status(
    ready: bool,
    contact_collection_declined: bool,
) -> str:
    if ready:
        return "ready"

    if contact_collection_declined:
        return "declined"

    return "draft"


def run_application_agent(
    data: ApplicationAgentInput,
) -> ApplicationAgentResult:

    # Сначала читаем переписку.
    extracted_contacts, declined = extract_contacts(
        messages=data.messages,
        current_draft=data.current_draft,
        contact_collection_declined=(
            data.contact_collection_declined
        ),
    )

    # Затем проверяем извлечённые контакты.
    contacts = prepare_contacts(extracted_contacts)

    missing_fields = get_missing_fields(contacts)

    ready = (
        data.application_requested
        and not declined
        and len(missing_fields) == 0
    )

    next_question = get_next_question(
        missing_fields,
        declined,
        data.application_requested,
    )

    status = get_status(
        ready,
        declined,
    )

    # Формируем резюме на основе истории диалога.
    summary = summarize_dialogue(data.messages)

    return ApplicationAgentResult(
        contacts=contacts,
        missing_fields=missing_fields,
        next_question=next_question,
        summary=summary,
        ready=ready,
        contact_collection_declined=declined,
        status=status,
    )
