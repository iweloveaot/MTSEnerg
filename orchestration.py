"""Shared RAG/application orchestration without web/database dependencies."""
import re
from time import perf_counter
from uuid import uuid4
from energytool_rag import consult

try:
    from application_agent import ApplicationAgentInput, Message, run_application_agent
    from application_agent.serializer import result_to_dict
except ModuleNotFoundError as exc:
    if exc.name != "application_agent":
        raise
    from mts_application_agent import ApplicationAgentInput, Message, run_application_agent
    from mts_application_serializer import result_to_dict

APPLICATION_REQUEST = re.compile(
    r"^\s*(?:хочу\s+оформить\s+заявку|оформить\s+заявку|оформите\s+заявку|"
    r"оставить\s+заявку|хочу\s+оставить\s+заявку)[.!\s]*$", re.IGNORECASE,
)


def process_message(message, *, model, index, session_id=None, history=None,
                    application_requested=False):
    started = perf_counter()
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Введите непустое сообщение")
    messages = []
    for item in history or []:
        if item.get("role") not in ("user", "assistant") or not isinstance(item.get("content"), str):
            raise ValueError("Некорректная история диалога")
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": message.strip()})
    requested = application_requested or any(
        item["role"] == "user" and APPLICATION_REQUEST.fullmatch(item["content"])
        for item in messages
    )
    session_id = session_id or str(uuid4())
    application = run_application_agent(ApplicationAgentInput(
        session_id=session_id, messages=[Message(**item) for item in messages],
        application_requested=bool(requested),
    ))
    sources, issue = [], None
    if application.next_question:
        answer, action = application.next_question, "contacts"
    elif application.ready:
        answer = "Данные заявки собраны. Они отображаются в карточке заявки; отправка менеджеру пока не подключена."
        action = "ready"
    else:
        consultation = consult(index, messages, model.generate_prompt)
        answer, action = consultation.answer, consultation.action
        sources = list(dict.fromkeys(source.path for source in consultation.sources))
        issue = consultation.generation_issue
    return {
        "answer": answer, "action": action, "session_id": session_id,
        "processing_time_ms": round((perf_counter() - started) * 1000, 2),
        "sources": sources, "application": result_to_dict(application),
        "generation_issue": issue,
    }
