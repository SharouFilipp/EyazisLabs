from __future__ import annotations

from grammar import POS_RU, TAG_RU, role_of

PHRASE = {"NOUN": "NP", "PROPN": "NP", "PRON": "NP", "NUM": "NP", "VERB": "VP", "AUX": "VP", "ADJ": "ADJP",
          "ADV": "ADVP", "ADP": "PP", "SCONJ": "SBAR", "DET": "DP", "CCONJ": "CONJP", "PART": "PRT"}
SUBJ = {"nsubj", "nsubjpass", "csubj", "expl"}


def dependency_tree(sent, fr_of: dict | None = None, skip: set | None = None) -> dict:
    fr_of, skip = fr_of or {}, skip or set()

    def node(t):
        return {"label": t.text, "sub": t.dep_, "tag": t.tag_, "pos": t.pos_, "i": t.i - sent.start,
                "fr": " ".join(fr_of.get(t.i, [])), "title": f"{t.text} — {TAG_RU.get(t.tag_, t.tag_)}; {role_of(t)}",
                "children": [node(c) for c in t.children if not c.is_space and c.i not in skip]}
    return node(sent.root)


def constituency_tree(sent, skip: set | None = None) -> dict:
    skip = skip or set()

    def leaf(t):
        return {"label": t.tag_, "children": [{"label": t.text, "leaf": True, "i": t.i - sent.start}],
                "title": TAG_RU.get(t.tag_, t.tag_)}

    def phrase(t):
        kids = [c for c in t.children if not c.is_space and c.i not in skip]
        if not kids:
            return leaf(t)
        label = PHRASE.get(t.pos_, "XP")
        subj = [c for c in kids if c.dep_ in SUBJ]
        if t.pos_ in ("VERB", "AUX") and subj and max(x.i for x in subj) < t.i:
            first = min(x.i for x in subj)
            rest = [c for c in kids if c.dep_ not in SUBJ]
            last = max([c.i for c in rest if not c.is_punct] + [t.i])
            front = [c for c in rest if c.i < first]
            tail = [c for c in rest if c.is_punct and c.i > last]
            vp_parts = sorted([c for c in rest if c not in front and c not in tail] + [t], key=lambda x: x.i)
            vp = {"label": "VP", "children": [leaf(x) if x.i == t.i else phrase(x) for x in vp_parts], "title": "глагольная группа"}
            ch = [phrase(x) for x in sorted(front + subj, key=lambda x: x.i)] + [vp] + [phrase(x) for x in tail]
            label = "SBAR" if t.dep_ != "ROOT" and any(c.dep_ == "mark" or c.tag_ in ("WRB", "WDT", "WP") for c in front + subj) else "S"
            return {"label": label, "children": ch, "title": "предложение / клауза"}
        parts = sorted(kids + [t], key=lambda x: x.i)
        return {"label": label, "children": [leaf(x) if x.i == t.i else phrase(x) for x in parts],
                "title": {"NP": "именная группа", "VP": "глагольная группа", "PP": "предложная группа",
                          "ADJP": "группа прилагательного", "ADVP": "группа наречия"}.get(label, label)}

    return phrase(sent.root)


def bracketed(tree: dict) -> str:
    if tree.get("leaf"):
        return tree["label"]
    inner = " ".join(bracketed(c) for c in tree["children"])
    return f"({tree['label']} {inner})"


def tokens_table(sent, fr_of: dict | None = None) -> list[dict]:
    fr_of = fr_of or {}
    return [{"i": t.i - sent.start, "text": t.text, "lemma": t.lemma_, "pos": t.pos_, "pos_ru": POS_RU.get(t.pos_, t.pos_),
             "tag": t.tag_, "tag_ru": TAG_RU.get(t.tag_, t.tag_), "dep": t.dep_, "role": role_of(t),
             "head": t.head.i - sent.start, "head_text": t.head.text, "fr": " ".join(fr_of.get(t.i, []))}
            for t in sent if not t.is_space]
