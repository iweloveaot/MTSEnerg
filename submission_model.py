"""Minimal OpenAI-compatible transport; only httpx is required on the platform."""
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    timeout: float = 60.0
    max_tokens: int = 1500
    max_tokens_limit: int = 6000

    @classmethod
    def from_env(cls):
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(Path(__file__).resolve().parent / ".env")
        return cls(
            os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            os.getenv("LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
            os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "")),
            float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            int(os.getenv("LLM_MAX_TOKENS", "1500")),
            int(os.getenv("LLM_MAX_TOKENS_LIMIT", "6000")),
        )


class ModelAdapter:
    def __init__(self, settings):
        self.settings = settings
        self._client = None

    def generate_prompt(self, messages):
        if not all((self.settings.api_key, self.settings.base_url, self.settings.model)):
            raise ValueError("Задайте LLM_API_KEY, LLM_BASE_URL и LLM_MODEL")
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=self.settings.timeout)
        if not 0 < self.settings.max_tokens <= self.settings.max_tokens_limit:
            raise ValueError("Нужно 0 < LLM_MAX_TOKENS <= LLM_MAX_TOKENS_LIMIT")
        budget = self.settings.max_tokens
        for attempt in range(3):
            payload = self._request(messages, budget)
            try:
                choice = payload["choices"][0]
                answer = choice["message"].get("content")
                finish = choice.get("finish_reason")
            except (KeyError, IndexError, TypeError, AttributeError):
                raise ValueError("Некорректный формат API: ожидается choices[0].message.content") from None
            if isinstance(answer, str) and answer.strip() and finish != "length":
                return answer.strip()
            if attempt < 2:
                if finish == "length":
                    # Some models spend the output budget before producing content.
                    budget = min(budget * 2, self.settings.max_tokens_limit)
                time.sleep(attempt + 1)
        usage = payload.get("usage") or {}
        tokens = usage.get("completion_tokens", "не указано") if isinstance(usage, dict) else "не указано"
        raise ValueError(
            "API модели не вернул полный текст ответа после 3 попыток: "
            f"finish_reason={finish}, completion_tokens={tokens}, max_tokens={budget}. "
            "При finish_reason=length увеличьте LLM_MAX_TOKENS / LLM_MAX_TOKENS_LIMIT. "
            "При пустом content с другой причиной проверьте доступность модели у провайдера."
        )

    def _request(self, messages, budget):
        for attempt in range(4):
            response = self._client.post(
                self.settings.base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + self.settings.api_key},
                json={"model": self.settings.model, "messages": messages,
                      "temperature": 0, "max_tokens": budget},
            )
            if response.status_code not in (429, 502, 503, 504) or attempt == 3:
                break
            try:
                delay = float(response.headers.get("Retry-After", 10 * (attempt + 1)))
            except ValueError:
                delay = 10 * (attempt + 1)
            time.sleep(min(60, max(1, delay)))
        if response.status_code != 200:
            raise RuntimeError(f"API модели: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise ValueError("API модели вернул некорректный JSON") from None

    def close(self):
        if self._client is not None:
            self._client.close()
