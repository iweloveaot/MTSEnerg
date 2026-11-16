"""Build Docker and check persistence. Run from an extracted full project."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8000'


def compose(*args):
    subprocess.run(['docker', 'compose', *args], cwd=ROOT, check=True)


def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(BASE + path, data=data,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def wait():
    for _ in range(60):
        try:
            if api('/api/health')['status'] == 'ok':
                return
        except (OSError, ValueError, KeyError):
            time.sleep(1)
    raise RuntimeError('Container did not become healthy')


def main():
    compose('up', '--build', '-d')
    wait()
    compose('exec', '-T', 'energytool', 'python', '-c',
            'from pathlib import Path; assert Path("/knowledge/knowledge-base.zip").is_file()')
    session = 'docker-check-' + str(uuid4())
    api('/api/chat', {'session_id': session, 'message': 'Оформить заявку'})
    result = api('/api/chat', {'session_id': session, 'message':
                 'Меня зовут Анна Иванова. Компания Ромашка. Телефон 89991234567.'})
    assert result['application']['ready'], 'Test application is not ready'
    expected = api('/api/sessions/' + session)
    assert len(expected['messages']) == 4
    compose('restart', 'energytool')
    wait()
    assert api('/api/sessions/' + session) == expected, 'Restart lost data'
    compose('up', '-d', '--force-recreate', 'energytool')
    wait()
    assert api('/api/sessions/' + session) == expected, 'Recreation lost data'
    assert api('/api/ready')['model'] == 'available', 'Model is unavailable'
    report = {'status': 'passed', 'session_id': session,
              'checks': ['build', 'knowledge_mount', 'application', 'restart', 'recreate', 'model']}
    output = ROOT / 'qa-local' / 'docker-result.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('DOCKER_CHECK_PASSED. See qa-local/docker-result.json')


if __name__ == '__main__':
    main()
