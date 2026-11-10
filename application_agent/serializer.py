
import json
from dataclasses import asdict

from .models import ApplicationAgentResult


def result_to_dict(
    result: ApplicationAgentResult,
) -> dict:
    """
    Преобразует результат агента
    в обычный словарь Python.

    Такой словарь удобно передавать
    через API и отображать в интерфейсе.
    """

    return asdict(result)


def result_to_json(
    result: ApplicationAgentResult,
) -> str:
    """
    Преобразует результат агента
    в JSON-строку.

    ensure_ascii=False сохраняет
    русский текст в читаемом виде.
    """

    data = result_to_dict(result)

    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )
