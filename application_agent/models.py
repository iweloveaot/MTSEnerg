from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Message:
    """
    Одно сообщение внутри диалога.
    """

    role: str
    content: str


@dataclass
class Contacts:
    """
    Контактные данные клиента.

    По требованиям кейса для заявки нужны:
    - ФИО;
    - телефон;
    - название компании.
    """

    full_name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None


@dataclass
class ApplicationSummary:
    """
    Краткое резюме разговора для менеджера.
    """

    problem: str = ""
    circumstances: str = ""
    discussed_solution: str = ""
    open_questions: List[str] = field(default_factory=list)


@dataclass
class ApplicationAgentInput:
    """
    Данные, которые агент получает на вход.
    """

    session_id: str
    messages: List[Message]

    current_draft: Contacts = field(
        default_factory=Contacts
    )

    contact_collection_declined: bool = False
    application_requested: bool = False

@dataclass
class ApplicationAgentResult:
    """
    Структурированный результат работы агента.
    """

    contacts: Contacts

    missing_fields: List[str]

    next_question: Optional[str]

    summary: ApplicationSummary

    ready: bool

    contact_collection_declined: bool

    status: str