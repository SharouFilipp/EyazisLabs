from __future__ import annotations

import re

import french as F

NOUN_RULES = [
    ("tion", "tion", "f"), ("sion", "sion", "f"), ("ity", "ité", "f"), ("ism", "isme", "m"), ("ist", "iste", "m"),
    ("ology", "ologie", "f"), ("graphy", "graphie", "f"), ("sophy", "sophie", "f"), ("ics", "ique", "f"),
    ("ence", "ence", "f"), ("ance", "ance", "f"), ("ment", "ment", "m"), ("ure", "ure", "f"),
    ("ogue", "ogue", "m"), ("age", "age", "m"), ("ude", "ude", "f"), ("ery", "erie", "f"),
    ("ncy", "nce", "f"), ("cy", "tie", "f"), ("ory", "oire", "f"), ("ary", "aire", "m"), ("or", "eur", "m"), ("er", "eur", "m"),
    ("ty", "té", "f"), ("ine", "ine", "f"), ("ism", "isme", "m"), ("phy", "phie", "f"), ("ia", "ie", "f"),
    ("y", "ie", "f"), ("e", "e", "f"),
]
ADJ_RULES = [
    ("ical", "ique"), ("ic", "ique"), ("ous", "eux"), ("ive", "if"), ("able", "able"), ("ible", "ible"),
    ("ant", "ant"), ("ent", "ent"), ("ular", "ulaire"), ("ary", "aire"), ("al", "al"), ("ile", "ile"),
    ("ed", "é"), ("ile", "ile"), ("ian", "ien"), ("ese", "ais"),
]
VERB_RULES = [("ize", "iser"), ("ise", "iser"), ("ify", "ifier"), ("ate", "er"), ("ute", "uer"), ("ect", "ecter"),
              ("ict", "ire"), ("ess", "esser"), ("ine", "iner"), ("e", "er"), ("", "er")]


def _cog(word: str, rules) -> tuple[str, str, str] | None:
    for r in rules:
        en_suf, fr_suf = r[0], r[1]
        if word.endswith(en_suf) and len(word) > len(en_suf) + 2:
            base = word[: len(word) - len(en_suf)] if en_suf else word
            return base + fr_suf, (r[2] if len(r) > 2 else None), f"-{en_suf or '∅'} → -{fr_suf}"
    return None


def suggest(lexicon, lemma: str, pos: str, word: str | None = None) -> dict | None:
    lemma = lemma.lower()
    word = (word or lemma).lower()
    if pos == "ADV" and word.endswith("ly"):
        for base in (word[:-2], word[:-3] + "y" if word.endswith("ily") else None,
                     word[:-4] if word.endswith("ally") else None, word[:-2] + "e"):
            a = base and lexicon.get(base, "ADJ")
            if a:
                from transfer import adverb_from_adj
                return {"fr": adverb_from_adj(a), "gender": None, "extra": "", "confidence": "высокая",
                        "rule": f"наречие от прилагательного {base} → {a['fr']}"}
    if pos in ("ADJ", "VERB") and word.endswith("ed"):
        for base in (word[:-2], word[:-1], word[:-3] if re.search(r"(.)\1ed$", word) else None):
            v = base and lexicon.get(base, "VERB")
            if v:
                _, inf, _ = F.split_verb(v["fr"])
                return {"fr": F.past_participle(inf), "gender": None, "extra": "", "confidence": "высокая",
                        "rule": f"причастие от глагола {base} → {v['fr']}"}
    if pos == "NOUN" and word.endswith("ing"):
        v = lexicon.get(lemma[:-3], "VERB") or lexicon.get(lemma[:-3] + "e", "VERB")
        if v:
            return {"fr": v["fr"], "gender": "m", "extra": "", "confidence": "низкая",
                    "rule": "отглагольное существительное: перевод глагола (проверьте форму)"}
    if pos in ("NOUN", "PROPN"):
        c = _cog(lemma, NOUN_RULES)
        if c:
            weak = c[2] in ("-er → -eur", "-e → -e", "-y → -ie")
            return {"fr": c[0], "gender": c[1] or "m", "extra": "", "confidence": "низкая" if weak else "средняя",
                    "rule": f"суффикс {c[2]}"}
    if pos == "ADJ":
        c = _cog(lemma, ADJ_RULES)
        if c:
            return {"fr": c[0], "gender": None, "extra": "", "confidence": "средняя", "rule": f"суффикс {c[2]}"}
    if pos == "VERB":
        c = _cog(lemma, VERB_RULES)
        if c:
            return {"fr": c[0], "gender": None, "extra": "", "confidence": "низкая" if c[2] in ("-∅ → -er", "-e → -er")
                    else "средняя", "rule": f"суффикс {c[2]}"}
    if pos == "ADV":
        a = _cog(lemma[:-2] if lemma.endswith("ly") else lemma, ADJ_RULES)
        if a:
            return {"fr": adverb_like(a[0]), "gender": None, "extra": "", "confidence": "низкая", "rule": "наречие по суффиксу"}
    return None


def adverb_like(adj: str) -> str:
    if adj.endswith("ant"):
        return adj[:-3] + "amment"
    if adj.endswith("ent"):
        return adj[:-3] + "emment"
    return F.adj_feminine(adj) + "ment"
