"""Build a flat competition ZIP without modifying participant source files."""
import argparse
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def build(output):
    sources = {name: (ROOT / name).read_text(encoding="utf-8-sig") for name in (
        "solution.py", "orchestration.py", "submission_model.py", "energytool_rag.py",
    )}
    for path in sorted((ROOT / "application_agent").glob("*.py")):
        name = "mts_application_" + ("agent" if path.stem == "__init__" else path.stem)
        # __init__ exports the actual agent, so give its implementation a distinct name.
        if path.stem == "agent":
            name = "mts_application_runner"
        text = path.read_text(encoding="utf-8-sig")
        def replace(match):
            module = "runner" if match[1] == "agent" else match[1]
            return "from mts_application_" + module + " import "
        text = re.sub(r"from \.(\w+) import ", replace, text)
        sources[name + ".py"] = text
    for name, source in sources.items():
        compile(source, name, "exec")
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, source in sources.items():
            archive.writestr(name, source.encode("utf-8"))
        archive.writestr("requirements.txt", "httpx==0.28.1\n")
    return Path(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="submission.zip")
    print(build(parser.parse_args().output))
