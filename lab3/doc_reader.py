"""Извлечение текста, абзацев и метаданных из документов PDF, DOCX, TXT."""
import statistics
from pathlib import Path

import pdfplumber
from docx import Document as DocxDocument

from text_processor import normalize, split_paragraphs

SUPPORTED = {".pdf", ".docx", ".txt"}


class ReadError(Exception):
    pass


def _pdf_paragraphs(path: Path) -> tuple[list[str], str | None, int]:
    """Абзацы PDF восстанавливаются по геометрии строк: новый абзац начинается,
    если вертикальный промежуток до строки заметно больше обычного межстрочного
    интервала или строка начинается с отступа (красная строка)."""
    paragraphs, current = [], []
    with pdfplumber.open(str(path)) as pdf:
        title = (pdf.metadata or {}).get("Title") or None
        pages = len(pdf.pages)
        for page in pdf.pages:
            lines = page.extract_text_lines(layout=False, strip=True)
            if not lines:
                continue
            gaps = [b["top"] - a["top"] for a, b in zip(lines, lines[1:]) if b["top"] > a["top"]]
            step = statistics.median(gaps) if gaps else 0
            left = min(l["x0"] for l in lines)
            prev = None
            for line in lines:
                text = line["text"].strip()
                if not text:
                    continue
                indent = line["x0"] - left > 12
                gap = prev is not None and step and line["top"] - prev["top"] > step * 1.35
                new_par = bool(indent or gap)
                if new_par and current:
                    paragraphs.append("\n".join(current))
                    current = []
                current.append(text)
                prev = line
            # абзац может продолжаться на следующей странице: границу страницы не считаем разрывом
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs, title, pages


def read_document(path: Path) -> dict:
    """Возвращает {title, pages, paragraphs}. Абзацы — нормализованные строки."""
    ext = path.suffix.lower()
    title, pages = None, 1
    if ext == ".pdf":
        raw_pars, title, pages = _pdf_paragraphs(path)
        raw = "\n\n".join(raw_pars)
    elif ext == ".docx":
        d = DocxDocument(str(path))
        title = d.core_properties.title or None
        raw = "\n\n".join(p.text for p in d.paragraphs if p.text.strip())
    elif ext == ".txt":
        data = path.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                raw = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        raise ReadError(f"Формат {ext} не поддерживается (допустимы PDF, DOCX, TXT)")

    paragraphs = split_paragraphs(normalize(raw))
    if not paragraphs or sum(len(p) for p in paragraphs) < 200:
        raise ReadError("Документ не содержит текстового слоя или слишком короткий (менее 200 символов)")

    # Заголовок — первый короткий абзац без точки в конце; он не участвует в реферировании
    first = paragraphs[0]
    if title and first.replace(" ", "") == title.replace(" ", ""):
        paragraphs = paragraphs[1:]
    elif len(first) < 160 and not first.endswith((".", "!", "?", "…")):
        title = title or first
        paragraphs = paragraphs[1:]
    return {"title": title or path.stem, "pages": pages, "paragraphs": paragraphs}
