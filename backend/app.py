from contextlib import asynccontextmanager
from typing import Annotated, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT, Settings
from .llm import ModelAdapter, ServiceError
from .service import ChatService
from .store import SessionStore


class ChatRequest(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=10000)]
    session_id: Annotated[Optional[str], Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] = None


def create_app(settings=None, model=None):
    settings = settings or Settings.from_env()
    model = model or ModelAdapter(settings)
    service = ChatService(model, SessionStore(settings.database))

    @asynccontextmanager
    async def lifespan(app):
        yield
        model.close()

    app = FastAPI(title="MTS Energytool", lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={
            "error": {"code": exc.code, "message": str(exc)},
        })

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/ready")
    def ready():
        model.check()
        return {"status": "ok", "model": "available"}

    @app.post("/api/chat")
    def chat(body: ChatRequest):
        if not body.message.strip():
            return JSONResponse(status_code=422, content={
                "error": {"code": "invalid_message", "message": "Введите текст сообщения."},
            })
        return service.chat(body.message, body.session_id)

    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
    return app
