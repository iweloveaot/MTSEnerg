"""Local adapter; the competition signature requires its official template."""
import argparse
import json
from backend.config import Settings
from backend.llm import ModelAdapter
from backend.service import process_message


def solve(message, history=None):
    """Independent test case, without persistent web session state."""
    model = ModelAdapter(Settings.from_env())
    try:
        return process_message(message, model=model, history=history)
    finally:
        model.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Проверка общего обработчика")
    parser.add_argument("message")
    args = parser.parse_args()
    print(json.dumps(solve(args.message), ensure_ascii=False, indent=2))
