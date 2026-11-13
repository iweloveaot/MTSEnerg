#!/usr/bin/env bash
# Проверки участника В: агент заявок и его интеграция с backend.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Не найден $PYTHON. Сначала создайте .venv с зависимостями проекта." >&2
  exit 1
fi
echo "=== Агент заявок: все unit- и регрессионные тесты ==="
"$PYTHON" -m unittest discover -s tests -q
echo "=== Контракт интеграции: существующий backend API ==="
"$PYTHON" -m unittest discover -s backend_tests -p 'test_integration.py' -q
echo "=== Все проверки зоны участника В прошли ==="
echo "Примечание: тесты сборки submission участника А не входят в этот набор."
echo "=== Frontend: проверка кнопок предложения заявки ==="
node --check frontend/app.js
node --test scripts/test_frontend_offer.cjs