"""Export the platform ZIP and a clean source package without private local data."""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

from build_submission import build

ROOT = Path(__file__).resolve().parent
ROOT_FILES = ('README.md', 'BACKEND.md', 'RELEASE_CHECKLIST.md', '.env.example',
              '.gitignore', '.dockerignore', 'Dockerfile', 'compose.yaml',
              'requirements.txt', 'requirements-dev.txt', 'solution.py',
              'submission_model.py', 'orchestration.py', 'energytool_rag.py',
              'build_submission.py', 'build_final_release.py', 'test_day4_v_regressions.py')
DIRS = ('backend', 'backend_tests', 'application_agent', 'consultation_agent', 'frontend', 'docs', 'scripts', 'tests')
SUFFIXES = {'.py', '.md', '.js', '.cjs', '.css', '.html', '.sh', '.ps1'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y%m%d-%H%M%S')
    output = ROOT / 'releases' / stamp
    output.mkdir(parents=True, exist_ok=False)
    previous = ROOT / 'submission.zip'
    if previous.exists():
        (output / 'previous').mkdir()
        shutil.copy2(previous, output / 'previous' / 'submission.zip')
    submission = build(output / 'submission.zip')
    paths = [ROOT / name for name in ROOT_FILES]
    for directory in DIRS:
        paths += [p for p in (ROOT / directory).rglob('*') if p.is_file()
                  and p.suffix in SUFFIXES and not any(x in ('__pycache__', 'data') for x in p.relative_to(ROOT).parts)]
    paths = sorted(set(paths))
    assert all(p.is_file() and not p.is_symlink() for p in paths)
    source = output / 'project-source.zip'
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for path in paths:
            info = ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    manifest = {'release_id': stamp, 'created_timezone': 'Europe/Moscow',
                'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'note': 'Snapshot includes current working files; git_head alone does not identify this release.',
                'status': 'candidate; Docker, live-model and presentation acceptance pending',
                'artifacts': {p.name: sha(p) for p in (submission, source)},
                'source_files': {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'RELEASE_CHECKLIST.md', output / 'RELEASE_CHECKLIST.md')
    artifacts = [submission, source, output / 'manifest.json', output / 'RELEASE_CHECKLIST.md']
    (output / 'SHA256SUMS.txt').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in artifacts), encoding='utf-8')
    shutil.copy2(submission, ROOT / 'submission.zip')
    print(output)


if __name__ == '__main__':
    main()
