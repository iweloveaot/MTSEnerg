"""Read Markdown sections from the organizer archive."""

import re
from pathlib import PurePosixPath
from zipfile import ZipFile

from .models import Source


HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*\r?$", re.MULTILINE)

def load_sources(archive_path) -> list[Source]:
    """Keep each Markdown section intact, including its lists and tables."""
    sources = []
    with ZipFile(archive_path) as archive:
        for item in sorted(archive.infolist(), key=lambda item: item.filename):
            path = PurePosixPath(item.filename)
            if (
                item.is_dir()
                or path.suffix.lower() not in {".md", ".txt"}
                or any(part.startswith((".", "__MACOSX")) for part in path.parts)
            ):
                continue
            text = archive.read(item).decode("utf-8-sig")
            document_id = path.with_suffix("").as_posix()
            matches = list(HEADING.finditer(text)) if path.suffix.lower() == ".md" else []
            headings = []
            start, line = 0, 1
            for index, match in enumerate([*matches, None]):
                end = match.start() if match else len(text)
                body = text[start:end].strip()
                if body:
                    sources.append(Source(
                        document_id, f"{document_id}#{index:02d}", path.as_posix(),
                        tuple(title for _, title in headings) or (path.stem,),
                        line, body,
                    ))
                if match:
                    level = len(match[1])
                    while headings and headings[-1][0] >= level:
                        headings.pop()
                    headings.append((level, match[2]))
                    start = match.end()
                    line = text.count("\n", 0, match.start()) + 1
                    if text[start:start + 1] == "\n":
                        start += 1
    if not sources:
        raise ValueError("В базе знаний нет непустых файлов Markdown или TXT.")
    return sources
