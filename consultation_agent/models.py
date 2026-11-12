"""Types shared by search and consultation."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Source:
    document_id: str
    section_id: str
    path: str
    headings: tuple[str, ...]
    line: int
    text: str


@dataclass(frozen=True)
class Hit:
    source: Source
    score: float


@dataclass(frozen=True)
class Consultation:
    action: str
    answer: str
    sources: tuple[Source, ...]
    generation_issue: Optional[str] = None
    offer_application: bool = False
