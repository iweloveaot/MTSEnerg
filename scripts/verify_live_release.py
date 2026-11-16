"""Run a small real-model check; keep answers locally, never log credentials."""
import json
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from energytool_rag import SearchIndex, SEARCH_VERSION, PROMPT_VERSION
from orchestration import process_message
from solution import knowledge_path
from submission_model import Settings, ModelAdapter


def main():
    output = ROOT / 'qa-local' / 'live_release.json'
    output.parent.mkdir(exist_ok=True)
    model = ModelAdapter(replace(Settings.from_env(), timeout=20))
    index = SearchIndex.from_zip(knowledge_path())
    rows = []
    try:
        for question in ('Можно ли вести учёт электроэнергии по отдельным цехам?',
                         'Какая погода завтра в Москве?'):
            started = perf_counter()
            try:
                result = process_message(question, model=model, index=index)
                rows.append({'question': question, 'result': result,
                             'elapsed_ms': round((perf_counter() - started) * 1000, 2)})
                print(json.dumps({'action': result['action'], 'generation_issue': result['generation_issue'],
                                  'elapsed_ms': rows[-1]['elapsed_ms']}, ensure_ascii=True), flush=True)
            except Exception as exc:
                rows.append({'error_type': type(exc).__name__})
                print('LIVE_CHECK_FAILED ' + type(exc).__name__, flush=True)
                break
    finally:
        model.close()
        output.write_text(json.dumps({'search': SEARCH_VERSION, 'prompt': PROMPT_VERSION,
                                      'cases': rows}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
