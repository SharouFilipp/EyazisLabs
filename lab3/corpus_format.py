import re

from text_processor import split_sentences

_HEAD = re.compile(r"^﻿?\s*title\s*:", re.I)


def is_labeled(text: str) -> bool:
    return bool(_HEAD.match(text)) and "\n===" in text


def parse_labeled(text: str) -> dict:
    head, body = text.lstrip("﻿").split("===", 1)
    meta = dict(line.split(":", 1) for line in head.strip().splitlines() if ":" in line)
    meta = {k.strip().lower(): v.strip() for k, v in meta.items()}
    lang = meta.get("lang", "fr")
    paragraphs, reference = [], []
    for block in re.split(r"\n\s*\n", body.strip()):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        parts = block.split("[*] ")
        clean, marks = parts[0], set()
        for part in parts[1:]:
            marks.add(len(clean))
            clean += part
        paragraphs.append(clean)
        for off, sent in split_sentences(clean, lang):
            if off in marks:
                reference.append(sent)
    return {"title": meta.get("title", ""), "lang": lang, "domain": meta.get("domain", "cs"),
            "keywords": [k.strip() for k in meta.get("keywords", "").split(";") if k.strip()],
            "paragraphs": paragraphs, "reference": reference}
