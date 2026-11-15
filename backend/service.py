from functools import lru_cache
from energytool_rag import SearchIndex
from orchestration import APPLICATION_REQUEST, process_message as orchestrate
from solution import knowledge_path
from uuid import uuid4


@lru_cache(maxsize=1)
def get_index():
    return SearchIndex.from_zip(knowledge_path())


def process_message(message, *, model, session_id=None, history=None, application_requested=False):
    if not isinstance(message, str) or not message.strip() or len(message) > 10000:
        raise ValueError("Сообщение должно содержать от 1 до 10000 символов.")
    return orchestrate(message, model=model, index=get_index(), session_id=session_id,
                       history=history, application_requested=application_requested)


class ChatService:
    def __init__(self, model, store):
        self.model, self.store = model, store

    def chat(self, message, session_id=None):
        session_id = session_id or str(uuid4())
        with self.store.lock(session_id):
            state = self.store.load(session_id)
            if state.get("status") == "closed":
                from .llm import ServiceError
                raise ServiceError("session_closed", "Диалог закрыт. Начните новый диалог.", 409)
            result = process_message(
                message, model=self.model, session_id=session_id,
                history=state["messages"], application_requested=state["application_requested"],
            )
            state["messages"].extend([
                {"role": "user", "content": message.strip()},
                {"role": "assistant", "content": result["answer"]},
            ])
            state["application_requested"] = state["application_requested"] or bool(APPLICATION_REQUEST.fullmatch(message))
            self.store.save(session_id, state, result["application"] if state["application_requested"] else None)
            return result

    def create_session(self):
        session_id = str(uuid4())
        self.store.save(session_id, {"messages": [], "application_requested": False, "status": "active"})
        return self.store.get(session_id)

    def close_session(self, session_id):
        with self.store.lock(session_id):
            if self.store.get(session_id) is None:
                return None
            state = self.store.load(session_id)
            state["status"] = "closed"
            self.store.save(session_id, state)
            return self.store.get(session_id)
