from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError
from .config import Settings


class ServiceError(Exception):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.status = code, status


SYSTEM_PROMPT = """Ты русскоязычный консультант МТС Energytool.
Сейчас поиск по базе знаний ещё не подключён. Прямо сообщай об этом,
если вопрос требует сведений о продуктах. Не придумывай цены, свойства,
тарифы и условия Energytool. Можешь приветствовать клиента и уточнять его задачу.
Не запрашивай контакты и не обещай отправку заявки: этим управляет приложение.
"""


class ModelAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    def _get_client(self):
        if not all((self.settings.api_key, self.settings.base_url, self.settings.model)):
            raise ServiceError("model_not_configured", "API модели не настроен.")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.api_key, base_url=self.settings.base_url,
                timeout=self.settings.timeout, max_retries=0,
            )
        return self._client

    def generate(self, messages):
        try:
            response = self._get_client().chat.completions.create(
                model=self.settings.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                max_tokens=800,
            )
            answer = response.choices[0].message.content
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("empty answer")
            return answer.strip()
        except ServiceError:
            raise
        except APITimeoutError:
            raise ServiceError("model_timeout", "Модель не ответила вовремя. Попробуйте ещё раз.", 504) from None
        except APIConnectionError:
            raise ServiceError("model_unavailable", "API модели временно недоступен.") from None
        except APIStatusError as exc:
            code = "model_auth_error" if exc.status_code in (401, 403) else "model_unavailable"
            raise ServiceError(code, "Не удалось обратиться к API модели. Попробуйте позже.") from None
        except (ValueError, IndexError, AttributeError, TypeError):
            raise ServiceError("invalid_model_response", "Модель вернула некорректный ответ.", 502) from None

    def check(self):
        self.generate([{"role": "user", "content": "Ответь одним словом: готов."}])

    def close(self):
        if self._client is not None:
            self._client.close()
