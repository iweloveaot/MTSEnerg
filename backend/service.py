import re
from time import perf_counter
from uuid import uuid4
from application_agent import ApplicationAgentInput, Message, run_application_agent
from application_agent.serializer import result_to_dict
from .llm import ServiceError

# Explicit opt-in for the existing frontend, which sends only text.
APPLICATION_REQUEST = re.compile(
    r"^\s*(?:хочу\s+оформить\s+заявку|оформить\s+заявку|оформите\s+заявку|"
    r"оставить\s+заявку|хочу\s+оставить\s+заявку)[.!\s]*$", re.IGNORECASE,
)


def process_message(message, *, model, session_id=None, history=None, application_requested=False):
    """Shared processing; history excludes the new message and is never mutated."""
    started = perf_counter()
    if not isinstance(message, str) or not message.strip() or len(message) > 10000:
        raise ValueError("Сообщение должно содержать от 1 до 10000 символов.")
    session_id = session_id or str(uuid4())
    messages = []
    for item in history or []:
        if item.get("role") not in ("user", "assistant") or not isinstance(item.get("content"), str):
            raise ValueError("История должна содержать сообщения user/assistant с текстом content.")
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": message.strip()})
    requested = application_requested or any(
        item["role"] == "user" and APPLICATION_REQUEST.fullmatch(item["content"])
        for item in messages
    )
    application = run_application_agent(ApplicationAgentInput(
        session_id=session_id, messages=[Message(**item) for item in messages],
        application_requested=requested,
    ))
    if application.next_question:
        answer = application.next_question
    elif application.ready:
        answer = "Данные заявки собраны. Они отображаются в карточке заявки; отправка менеджеру пока не подключена."
    else:
        answer = model.generate(messages[-40:])
    if not isinstance(answer, str) or not answer.strip():
        raise ServiceError("invalid_model_response", "Модель вернула некорректный ответ.", 502)
    return {
        "answer": answer, "session_id": session_id,
        "processing_time_ms": round((perf_counter() - started) * 1000, 2),
        "sources": [], "application": result_to_dict(application),
    }


class ChatService:
    def __init__(self, model, store):
        self.model, self.store = model, store

    def chat(self, message, session_id=None):
        session_id = session_id or str(uuid4())
        with self.store.lock(session_id):
            state = self.store.load(session_id)
            result = process_message(
                message, model=self.model, session_id=session_id,
                history=state["messages"], application_requested=state["application_requested"],
            )
            state["messages"].extend([
                {"role": "user", "content": message.strip()},
                {"role": "assistant", "content": result["answer"]},
            ])
            state["application_requested"] = state["application_requested"] or bool(APPLICATION_REQUEST.fullmatch(message))
            self.store.save(session_id, state)
            return result
