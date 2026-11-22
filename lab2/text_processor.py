import re
import unicodedata
from typing import List

WORD_RE = re.compile(r"[a-zà-öø-ÿœæ]+'?")
SENTENCE_RE = re.compile(r'(?<=[.!?;:])\s+')


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    text = text.replace('’', "'").replace('ʼ', "'").replace('`', "'")
    text = re.sub(r'-\s*\n\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()


def tokenize(text: str) -> List[str]:
    return WORD_RE.findall(text)


def sentences(text: str) -> List[str]:
    return [s for s in SENTENCE_RE.split(text) if s.strip()]
