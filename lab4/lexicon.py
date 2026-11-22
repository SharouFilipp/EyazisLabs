from __future__ import annotations

from collections import defaultdict
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent / "data" / "seed"
LEMMA_ALIASES = {"simplifie": "simplify", "hat": "hate", "datum": "data", "analyse": "analyze",
                 "behaviour": "behavior", "neurone": "neuron", "studie": "study", "verifie": "verify"}
POS_GROUPS = {"PROPN": ("PROPN", "NOUN"), "NOUN": ("NOUN", "PROPN"), "AUX": ("VERB",), "VERB": ("VERB",),
              "ADJ": ("ADJ",), "ADV": ("ADV",), "ADP": ("ADP",), "SCONJ": ("SCONJ", "ADP"), "CCONJ": ("CCONJ",),
              "DET": ("DET",), "PRON": ("PRON",), "NUM": ("NUM",), "PART": ("PART",)}


def parse_extra(s: str | None) -> dict:
    d = {}
    for part in (s or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            d[k.strip()] = v.strip()
        else:
            d[part] = True
    return d


def read_dict_file(f: Path) -> list[dict]:
    words = []
    for line in Path(f).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        en, pos, fr, g, extra, dom = (line.split("|") + [""] * 6)[:6]
        words.append({"en": en.strip().lower(), "pos": pos.strip(), "fr": fr.strip(), "gender": g.strip() or None,
                      "extra": extra.strip(), "domain": dom.strip() or None})
    return words


def read_seed() -> tuple[list[dict], list[dict]]:
    words, phrases = [], []
    for f in sorted(SEED_DIR.glob("dict_*.txt")):
        words += read_dict_file(f)
    for line in (SEED_DIR / "phrases.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        en, fr, kind, extra = (line.split("|") + [""] * 4)[:4]
        phrases.append({"en": en.strip().lower(), "fr": fr.strip(), "kind": kind.strip(), "extra": extra.strip()})
    return words, phrases


class Lexicon:
    def __init__(self, words: list[dict], phrases: list[dict]):
        self.entries: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for w in words:
            e = dict(w)
            e["x"] = parse_extra(w.get("extra"))
            self.entries[(w["en"], w["pos"])].append(e)
        self.phrases: dict[str, list[dict]] = defaultdict(list)
        for p in phrases:
            e = dict(p)
            e["x"] = parse_extra(p.get("extra"))
            e["seq"] = tuple(p["en"].split())
            if e["kind"] == "NOUN" and "m" in e["x"]:
                e["gender"] = "m"
            elif e["kind"] == "NOUN" and "f" in e["x"]:
                e["gender"] = "f"
            self.phrases[e["seq"][0]].append(e)
        for (en, pos), lst in list(self.entries.items()):
            if pos == "PROPN" and " " in en:
                for w in lst:
                    seq = tuple(en.split())
                    self.phrases[seq[0]].append({"en": en, "fr": w["fr"], "kind": "PROPN", "seq": seq,
                                                 "x": w["x"], "gender": w["gender"]})
        for lst in self.phrases.values():
            lst.sort(key=lambda p: -len(p["seq"]))

    @classmethod
    def from_seed(cls, *extra_files) -> "Lexicon":
        words, phrases = read_seed()
        for f in extra_files:
            words += read_dict_file(f)
        return cls(words, phrases)

    @classmethod
    def from_db(cls, cur) -> "Lexicon":
        cur.execute("SELECT en, pos, fr, gender, extra, domain FROM dictionary ORDER BY id")
        words = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT en, fr, kind, extra FROM phrases ORDER BY id")
        phrases = [dict(r) for r in cur.fetchall()]
        return cls(words, phrases)

    def size(self) -> dict:
        return {"words": sum(len(v) for v in self.entries.values()), "lemmas": len(self.entries),
                "phrases": sum(len(v) for v in self.phrases.values())}

    def get(self, lemma: str, pos: str, domain: str | None = None) -> dict | None:
        cands = []
        for p in POS_GROUPS.get(pos, (pos,)):
            cands = self.entries.get((lemma, p))
            if cands:
                break
        if not cands:
            return None
        for c in cands:
            if domain and c["domain"] == domain:
                return c
        for c in cands:
            if not c["domain"]:
                return c
        return cands[0]

    def domain_votes(self, lemmas) -> dict:
        votes = {"cs": 0, "lit": 0}
        for lemma, pos in lemmas:
            for p in POS_GROUPS.get(pos, (pos,)):
                doms = {c["domain"] for c in self.entries.get((lemma, p), [])}
                if doms == {"cs"}:
                    votes["cs"] += 1
                elif doms == {"lit"}:
                    votes["lit"] += 1
                if doms:
                    break
        return votes
