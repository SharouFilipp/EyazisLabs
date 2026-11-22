import re
import threading
import unicodedata
from collections import Counter
from functools import lru_cache

import snowballstemmer

from stopwords import LANG_MARKERS, STOPWORDS

LANG_NAMES = {"fr": "французский", "it": "итальянский"}
DOMAIN_NAMES = {"cs": "научная статья (computer science)", "lit": "сочинение по литературе"}

_STEMMER_NAMES = {"fr": "french", "it": "italian"}
_local = threading.local()

LETTERS = "a-zà-öø-ÿœæ"
WORD_RE = re.compile(rf"[{LETTERS}]+", re.IGNORECASE)
RAW_TOKEN_RE = re.compile(r"[\w’']+", re.UNICODE)
ROMAN_RE = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")

ABBREVIATIONS = {
    "fr": {"m", "mm", "mme", "mlle", "dr", "pr", "st", "ste", "etc", "ex", "cf", "p", "pp", "fig",
           "vol", "chap", "env", "av", "apr", "j.-c", "n", "no", "éd", "art", "t"},
    "it": {"sig", "sigg", "dott", "prof", "ing", "avv", "ecc", "es", "cfr", "pag", "pagg", "fig",
           "vol", "cap", "s", "ss", "sec", "n", "nn", "art", "ca", "a.c", "d.c"},
}

DOMAIN_CUES = {
    "cs": {
        "fr": "algorithme donnée programme ordinateur réseau logiciel système calcul mémoire processeur "
              "langage code informatique machine apprentissage requête complexité serveur".split(),
        "it": "algoritmo dati programma calcolatore rete software sistema calcolo memoria processore "
              "linguaggio codice informatica macchina protocollo processo file server chiave".split(),
    },
    "lit": {
        "fr": "roman poète poésie personnage héros auteur écrivain œuvre récit recueil poème narrateur "
              "littérature amour héroïne style lecteur".split(),
        "it": "romanzo poeta poesia personaggio protagonista autore scrittore opera racconto poema "
              "narratore letteratura amore stile lettore canto".split(),
    },
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("’", "'").replace("ʼ", "'").replace(" ", " ").replace(" ", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    return text


def split_paragraphs(text: str) -> list[str]:
    paras = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if block:
            paras.append(block)
    return paras


_SENT_END = re.compile(r"([.!?…]+)([»\"”)]*)(\s+)(?=[«\"“(]?\s?[A-ZÀ-ÖØ-ÞŒ0-9])")


def split_sentences(paragraph: str, lang: str = "fr") -> list[tuple[int, str]]:
    abbr = ABBREVIATIONS.get(lang, set())
    result, start = [], 0
    for m in _SENT_END.finditer(paragraph):
        if m.group(1) == ".":
            prev = re.search(r"([\w.\-]+)$", paragraph[start:m.start(1)])
            if prev:
                word = prev.group(1).lower()
                if word in abbr or (len(word) == 1 and word.isalpha()):
                    continue
        sent = paragraph[start:m.end(2)].strip()
        if sent:
            result.append((start, sent))
        start = m.end(3)
    tail = paragraph[start:].strip()
    if tail:
        result.append((start, tail))
    return result


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(normalize(text))]


def detect_language(text: str) -> tuple[str, dict]:
    tokens = words(text)
    n = max(len(tokens), 1)
    scores = {lang: sum(1 for t in tokens if t in markers) / n for lang, markers in LANG_MARKERS.items()}
    return max(scores, key=scores.get), scores


def _stemmer(lang: str):
    cache = getattr(_local, "stemmers", None)
    if cache is None:
        cache = _local.stemmers = {}
    if lang not in cache:
        cache[lang] = snowballstemmer.stemmer(_STEMMER_NAMES[lang])
    return cache[lang]


@lru_cache(maxsize=200_000)
def stem(word: str, lang: str) -> str:
    return _stemmer(lang).stemWord(word)


def is_term(token: str, lang: str) -> bool:
    return len(token) >= 3 and token not in STOPWORDS[lang] and not ROMAN_RE.match(token)


def terms(text: str, lang: str) -> list[tuple[str, str]]:
    out = []
    for raw in RAW_TOKEN_RE.findall(normalize(text)):
        if any(ch.isdigit() for ch in raw) or "_" in raw:
            continue
        for w in WORD_RE.findall(raw):
            w = w.lower()
            if is_term(w, lang):
                out.append((stem(w, lang), w))
    return out


_DOMAIN_STEMS = {
    dom: {lang: {stem(w, lang) for w in ws} for lang, ws in by_lang.items()}
    for dom, by_lang in DOMAIN_CUES.items()
}


def detect_domain(text: str, lang: str) -> tuple[str, dict]:
    stems = Counter(s for s, _ in terms(text, lang))
    scores = {dom: sum(stems[s] for s in by_lang[lang]) for dom, by_lang in _DOMAIN_STEMS.items()}
    return max(scores, key=scores.get), scores
