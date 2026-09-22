"""Index the four original port-80 learning pages into the shared RAG corpus."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

from app.core.database import SessionLocal
from app.services.rag_service import RAGService


PAGES = (
    ("01", "80 학습 · 선물과 옵션"),
    ("02", "80 학습 · 펀드 · ETF"),
    ("03", "80 학습 · 채권 · 코인"),
    ("04", "80 학습 · 자산배분 · 퀀트"),
)


class MainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "svg"}:
            self.ignored += 1
        if tag in {"p", "h1", "h2", "h3", "h4", "li", "tr", "section", "article", "div", "br"}:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def page_text(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    match = re.search(r'<main id="app">(.*?)</main>', html, re.DOTALL)
    if not match:
        raise RuntimeError(f"main content not found: {path}")
    parser = MainTextParser()
    parser.feed(match.group(1))
    return parser.text()


def main() -> None:
    base = Path("/app/frontend/days")
    rag = RAGService()
    session = SessionLocal()
    try:
        total = 0
        for number, title in PAGES:
            content = page_text(base / f"{number}.html")
            count = rag.ingest_text(
                db=session,
                document_id=f"legacy-80-learning-{number}",
                title=title,
                content=content,
                domain="general",
            )
            total += count
            print(f"{number}: {count} chunks", flush=True)
        print(f"completed: {total} shared learning chunks")
    finally:
        session.close()


if __name__ == "__main__":
    main()
