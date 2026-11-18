"""Формирование тестовой коллекции: из исходных текстов corpus/src/*.txt
создаются PDF-документы corpus/test/*.pdf и файл эталонной разметки labels.json.

Формат исходного файла:
    title: Заголовок
    lang: fr | it
    domain: cs | lit
    keywords: ключевое слово; ...
    ===
    Абзацы, разделённые пустой строкой. Метка [*] перед предложением
    означает, что эксперт включил его в эталонный реферат.

Запуск: uv run python tools/build_corpus.py
"""
import json
import re
import sys
from pathlib import Path

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from corpus_format import parse_labeled  # noqa: E402

SRC, OUT = ROOT / "corpus" / "src", ROOT / "corpus" / "test"

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("C:/Windows/Fonts")]


def register_fonts():
    for d in FONT_DIRS:
        if (d / "DejaVuSerif.ttf").exists():
            pdfmetrics.registerFont(TTFont("Body", str(d / "DejaVuSerif.ttf")))
            pdfmetrics.registerFont(TTFont("Body-Bold", str(d / "DejaVuSerif-Bold.ttf")))
            return
        if (d / "times.ttf").exists():
            pdfmetrics.registerFont(TTFont("Body", str(d / "times.ttf")))
            pdfmetrics.registerFont(TTFont("Body-Bold", str(d / "timesbd.ttf")))
            return
    raise SystemExit("Не найден шрифт с поддержкой диакритики")


def parse(path: Path) -> dict:
    return parse_labeled(path.read_text(encoding="utf-8"))


def make_pdf(doc: dict, path: Path):
    title_st = ParagraphStyle("t", fontName="Body-Bold", fontSize=14, leading=18, spaceAfter=14)
    body_st = ParagraphStyle("b", fontName="Body", fontSize=11, leading=15, alignment=TA_JUSTIFY,
                             firstLineIndent=0.8 * cm, spaceAfter=6)
    story = [Paragraph(doc["title"], title_st)]
    for p in doc["paragraphs"]:
        story.append(Paragraph(p.replace("&", "&amp;").replace("<", "&lt;"), body_st))
    story.append(Spacer(1, 1))
    pdf = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=doc["title"],
                            author="Тестовая коллекция ЛР3", lang=doc["lang"])
    pdf.build(story)


def main():
    register_fonts()
    OUT.mkdir(parents=True, exist_ok=True)
    labels = {}
    for src in sorted(SRC.glob("*.txt")):
        doc = parse(src)
        name = src.stem + ".pdf"
        make_pdf(doc, OUT / name)
        chars = sum(len(p) for p in doc["paragraphs"])
        labels[name] = {"title": doc["title"], "lang": doc["lang"], "domain": doc["domain"],
                        "keywords": doc["keywords"], "reference": doc["reference"], "chars": chars}
        print(f"{name:16} {doc['lang']} {doc['domain']:3} символов={chars:5} абзацев={len(doc['paragraphs']):2} "
              f"эталон={len(doc['reference'])}")
    (OUT / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
