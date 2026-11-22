from __future__ import annotations

import re
import time
from collections import Counter

import french as F
import syntax
from grammar import LexemeEntry, POS_RU, TAG_RU, role_of, morph_ru
from lexicon import LEMMA_ALIASES, Lexicon

PUNCT_MAP = {"``": "«", "''": "»", "—": "—", "–": "–"}
SUBJ_PRON = {"i": (1, False, None, "je"), "you": (2, True, None, "vous"), "he": (3, False, "m", "il"),
             "she": (3, False, "f", "elle"), "it": (3, False, None, "il"), "we": (1, True, None, "nous"),
             "they": (3, True, None, "ils"), "one": (3, False, None, "on")}
OBJ_CLITIC = {"me": ("me", "me"), "you": ("vous", "vous"), "him": ("le", "lui"), "her": ("la", "lui"),
              "us": ("nous", "nous"), "them": ("les", "leur"), "it": ("le", "lui")}
STRESSED = {"me": "moi", "you": "vous", "him": "lui", "her": "elle", "us": "nous", "them": "eux", "it": "cela",
            "i": "moi", "he": "lui", "she": "elle", "we": "nous", "they": "eux", "himself": "lui-même",
            "herself": "elle-même", "itself": "lui-même", "themselves": "eux-mêmes"}
POSS_PRON = {"my": (1, False), "your": (2, True), "his": (3, False), "her": (3, False), "its": (3, False),
             "our": (1, True), "their": (3, True)}
MODALS = {"can": ("pouvoir", "pres"), "could": ("pouvoir", "cond"), "may": ("pouvoir", "pres"),
          "might": ("pouvoir", "cond"), "must": ("devoir", "pres"), "should": ("devoir", "cond"),
          "will": (None, "fut"), "shall": (None, "fut"), "would": (None, "cond"), "'ll": (None, "fut"),
          "wo": (None, "fut"), "'d": (None, "cond")}
STATIVE = {"be", "have", "want", "know", "believe", "seem", "need", "contain", "belong", "exist"}
PARTITIVE = {"memory", "kindness", "money", "water", "bread", "time", "speech", "energy", "space", "courage",
             "information", "work", "help", "power", "patience", "food", "light"}
WORK_NOUNS = {"novel", "book", "play", "poem", "work", "tragedy", "painting", "story", "essay", "comedy",
              "opera", "song", "film", "article", "drama", "letter", "symphony"}
QUANT_ADJ = {"many", "several", "few", "most", "less", "more", "much", "numerous", "other"}
TIME_NOUNS = {"year", "day", "week", "month", "hour", "minute", "second", "century", "time", "decade"}
REL_WORDS = {"that", "which", "who", "whom"}
VOWEL_RE = re.compile(r"^[aeiouyàâéèêëîïôœæ]", re.I)


def it(t, k="w", unk=False, src=None, **kw):
    d = {"t": t, "k": k, "src": src}
    if unk:
        d["unk"] = True
    d.update(kw)
    return d


class Realizer:

    def __init__(self, tr: "Translator", sent, domain: str | None):
        self.tr, self.lex, self.sent, self.domain = tr, tr.lex, sent, domain
        self.over: dict[int, dict] = {}
        self.consumed: set[int] = set()
        self.fixed: dict[int, str] = {}
        self.status: dict[int, str] = {}
        self.fr_of: dict[int, list[str]] = {}
        self.skip: set[int] = set()
        self.phrase_head: dict[int, int] = {}
        self.match_phrases()

    def lemma(self, t) -> str:
        l = t.lemma_.lower()
        return LEMMA_ALIASES.get(l, l)

    def lookup(self, t, pos=None):
        pos = pos or t.pos_
        keys = [self.lemma(t), t.lower_]
        for k in keys:
            e = self.lex.get(k, pos, self.domain)
            if e:
                return e
        if pos in ("ADJ", "VERB") and t.tag_ in ("VBN", "JJ") and t.lower_.endswith("ed"):
            for k in (t.lower_[:-2], t.lower_[:-1], self.lemma(t)):
                v = self.lex.get(k, "VERB", self.domain)
                if v:
                    _, inf, rest = F.split_verb(v["fr"])
                    return {"fr": F.past_participle(inf), "x": {}, "gender": None, "domain": None, "derived": "pp"}
        if pos == "ADV" and t.lower_.endswith("ly"):
            low = t.lower_
            for base in (low[:-2], low[:-3] + "y" if low.endswith("ily") else None, low[:-4] if low.endswith("ally") else None,
                         low[:-2] + "e", low[:-4] + "al" if low.endswith("ally") else None):
                if not base:
                    continue
                a = self.lex.get(base, "ADJ", self.domain)
                if a:
                    return {"fr": adverb_from_adj(a), "x": {}, "gender": None, "domain": None, "derived": "ly"}
        if pos == "PROPN":
            return None
        if pos == "NOUN" and t.tag_ in ("NNP", "NNPS"):
            return None
        return None

    def match_phrases(self):
        toks = list(self.sent)
        n = len(toks)
        i = 0
        while i < n:
            t = toks[i]
            cands = self.lex.phrases.get(self.lemma(t), []) + self.lex.phrases.get(t.lower_, [])
            done = False
            for p in cands:
                L = len(p["seq"])
                if i + L > n:
                    continue
                span = toks[i:i + L]
                if all(self.lemma(x) == w or x.lower_ == w for x, w in zip(span, p["seq"])) and \
                        not any(x.i in self.consumed or x.i in self.over for x in span):
                    self.apply_phrase(p, span)
                    i += L
                    done = True
                    break
            if not done:
                i += 1

    def apply_phrase(self, p, span):
        ids = {x.i for x in span}
        kind = p["kind"]
        if kind == "FIX":
            first = span[0]
            self.fixed[first.i] = p["fr"]
            self.over[first.i] = {"kind": "FIX", "fr": p["fr"]}
            for x in span[1:]:
                self.consumed.add(x.i)
            for x in span:
                self.status[x.i] = "phrase"
            return
        if kind == "VERB":
            head = next((x for x in span if x.pos_ in ("VERB", "AUX") and x.dep_ not in ("aux", "auxpass")), None) \
                or next((x for x in span if x.pos_ in ("VERB", "AUX")), span[0])
            self.over[head.i] = {"kind": "VERB", "fr": p["fr"], "x": p["x"]}
            for x in span:
                self.phrase_head[x.i] = head.i
                if x.i != head.i:
                    self.consumed.add(x.i)
                    if x.pos_ == "ADP" and p["x"].get("on") and x.lower_ in ("about", "of", "on", "to", "at", "for"):
                        self.fixed[x.i] = p["x"]["on"]
                self.status[x.i] = "phrase"
            return
        tops = [x for x in span if x.head.i not in ids or x.head.i == x.i]
        head = tops[0] if len(tops) == 1 and tops[0].pos_ in ("NOUN", "PROPN") else \
            next((x for x in reversed(span) if x.pos_ in ("NOUN", "PROPN")), tops[0] if tops else span[-1])
        self.over[head.i] = {"kind": kind, "fr": p["fr"], "x": p["x"], "gender": p.get("gender"), "span": ids}
        for x in span:
            if x.i != head.i:
                self.consumed.add(x.i)
            self.status[x.i] = "phrase"

    def noun_info(self, t) -> dict:
        o = self.over.get(t.i)
        plural = t.tag_ in ("NNS", "NNPS") or "Number=Plur" in str(t.morph)
        if self.lemma(t) == "people":
            plural = True
        if o and o["kind"] in ("NOUN", "PROPN"):
            x = o["x"]
            g = o.get("gender") or ("f" if "f" in x else "m")
            fr = o["fr"]
            if o["kind"] == "PROPN":
                plural = False
            if plural and kind_plural(fr, x):
                fr = F.noun_plural(fr, x.get("pl"))
            return {"fr": fr, "g": g, "pl": plural, "x": x, "known": True, "proper": o["kind"] == "PROPN"}
        if t.pos_ == "PROPN" or t.tag_ in ("NNP", "NNPS"):
            e = self._propn(t.lower_) or self._propn(self.lemma(t))
            common = None if e else (self.lex.get(self.lemma(t), "NOUN", self.domain) or self.lex.get(t.lower_, "NOUN", self.domain))
            if common and not (t.i > self.sent.start and t.text[0].isupper() and t.lower_ in self.tr.names_like):
                self.status.setdefault(t.i, "dict")
                fr = F.noun_plural(common["fr"], common["x"].get("pl")) if plural else common["fr"]
                return {"fr": fr, "g": common["gender"] or "m", "pl": plural, "x": common["x"], "known": True, "proper": False}
            if e:
                self.status[t.i] = "dict"
                return {"fr": e["fr"], "g": e["gender"] or "m", "pl": False, "x": e["x"], "known": True, "proper": True}
            self.status.setdefault(t.i, "proper")
            return {"fr": t.text, "g": "m", "pl": False, "x": {}, "known": True, "proper": True}
        e = self.lookup(t, "NOUN") or (self.lex.get(t.lower_, "NOUN", self.domain) if t.tag_ == "VBG" else None)
        if e:
            self.status.setdefault(t.i, "dict")
            fr = F.noun_plural(e["fr"], e["x"].get("pl")) if plural else e["fr"]
            if self.lemma(t) == "data" or t.lower_ == "data":
                plural, fr = True, "données"
            return {"fr": fr, "g": e["gender"] or "m", "pl": plural, "x": e["x"], "known": True, "proper": False}
        for k in (t.lower_[:-1] if t.lower_.endswith("s") else None, t.lower_[:-2] if t.lower_.endswith("es") else None):
            e = self.lex.get(k, "NOUN", self.domain) if k else None
            if e:
                self.status.setdefault(t.i, "dict")
                return {"fr": F.noun_plural(e["fr"], e["x"].get("pl")) if plural else e["fr"], "g": e["gender"] or "m",
                        "pl": plural, "x": e["x"], "known": True, "proper": False}
        if any(ch.isupper() for ch in t.text[1:]) or (t.text[0].isupper() and t.i > self.sent.start):
            self.status[t.i] = "proper"
            return {"fr": t.text, "g": "m", "pl": False, "x": {}, "known": True, "proper": True}
        self.status.setdefault(t.i, "unknown")
        return {"fr": t.text, "g": "m", "pl": plural, "x": {}, "known": False, "proper": False}

    def _propn(self, key):
        lst = self.lex.entries.get((key, "PROPN"))
        return lst[0] if lst else None

    def remember(self, t, info, role):
        if info.get("proper") and not info["x"].get("country"):
            g = "f" if t.lower_ in self.tr.female_names else "m"
        else:
            g = info["g"]
        self.tr.memory.append({"g": g, "pl": info["pl"], "role": role, "word": info["fr"]})
        self.tr.memory = self.tr.memory[-12:]

    def antecedent(self, plural: bool, prefer_subject: bool = True) -> str:
        mem = [m for m in reversed(self.tr.memory) if m["pl"] == plural]
        if prefer_subject:
            subj = [m for m in mem if m["role"] == "subj"]
            if subj:
                return subj[0]["g"]
        return mem[0]["g"] if mem else "m"

    def subj_features(self, s, verb=None) -> dict:
        if s is None:
            return {"person": 3, "pl": False, "g": "m"}
        low = s.lower_
        if low in REL_WORDS and verb is not None and verb.dep_ == "relcl":
            ant = verb.head
            return self.np_features(ant)
        if s.pos_ == "PRON" and low in SUBJ_PRON:
            person, pl, g, _ = SUBJ_PRON[low]
            if g is None:
                g = self.antecedent(pl) if low in ("it", "they") else "m"
            return {"person": person, "pl": pl, "g": g}
        return self.np_features(s)

    def np_features(self, n) -> dict:
        if n.pos_ == "PRON" and n.lower_ in SUBJ_PRON:
            return self.subj_features(n)
        if n.lower_ == "one":
            return {"person": 3, "pl": False, "g": "m"}
        info = self.noun_info(n)
        pl = info["pl"] or any(c.dep_ == "conj" for c in n.children)
        return {"person": 3, "pl": pl, "g": info["g"]}

    def mark(self, t, items):
        self.fr_of.setdefault(t.i, []).extend(x["t"] for x in items if x.get("src") == t.i)
        return items

    def render(self, t, ctx=None) -> list[dict]:
        ctx = ctx or {}
        if t.i in self.fixed and t.i not in self.consumed:
            words = [it(w, "w", src=t.i) for w in self.fixed[t.i].split(" ")]
            return self.mark(t, self.with_children(t, words, ctx, skip_consumed=True))
        if t.i in self.skip:
            return []
        if t.i in self.consumed:
            if t.pos_ == "ADP" and any(c.dep_ == "pobj" and c.i not in self.consumed for c in t.children):
                return self.render_pp(t, ctx)
            items = [it(w, "w", src=t.i) for w in self.fixed[t.i].split(" ")] if t.i in self.fixed else []
            return self.with_children(t, items, ctx, skip_consumed=True)
        if t.is_punct:
            self.status[t.i] = "punct"
            return [it(PUNCT_MAP.get(t.text, t.text), "punct", src=t.i)]
        if t.lower_ == "one" and any(c.dep_ == "prep" and c.lower_ == "of" for c in t.children):
            return self.render_one_of(t, ctx)
        if t.i in self.over and self.over[t.i]["kind"] in ("NOUN", "PROPN"):
            return self.render_np(t, ctx)
        if t.pos_ in ("NOUN", "PROPN") and t.dep_ in ("ccomp", "xcomp") and not ctx.get("role"):
            ctx = {**ctx, "role": "obj"}
        if t.tag_ == "VBG" and t.dep_ in ("nsubj", "nsubjpass", "csubj") and not any(c.dep_ == "aux" for c in t.children):
            if self.lex.get(t.lower_, "NOUN", self.domain):
                return self.render_np(t, {**ctx, "role": "subj"})
        if t.pos_ in ("VERB", "AUX") and t.dep_ not in ("aux", "auxpass"):
            if t.dep_ in ("amod",) and t.tag_ in ("VBN", "VBG"):
                return self.render_adjp(t, ctx)
            return self.render_clause(t, ctx)
        if t.pos_ in ("NOUN", "PROPN") or (t.pos_ == "NUM" and ctx.get("role") in ("subj", "obj") and
                                             any(c.dep_ in ("det", "amod", "prep") for c in t.children)):
            return self.render_np(t, ctx)
        if t.pos_ == "PRON":
            return self.render_pron(t, ctx)
        if t.pos_ == "ADJ":
            return self.render_adjp(t, ctx)
        if t.pos_ == "ADP" or t.dep_ in ("prep", "agent"):
            return self.render_pp(t, ctx)
        if t.pos_ == "NUM":
            return self.render_word(t, ctx, pos="NUM")
        return self.render_word(t, ctx)

    def render_word(self, t, ctx, pos=None):
        if t.like_num and re.fullmatch(r"[\d.,]+", t.text):
            self.status[t.i] = "proper"
            items = [it(t.text, src=t.i)]
        else:
            e = self.lookup(t, pos)
            if e:
                self.status.setdefault(t.i, "dict" if not e.get("derived") else "rule")
                fr = e["fr"]
                if t.pos_ in ("SCONJ", "ADP") and t.lower_ == "that":
                    fr = "que"
                items = [it(w, src=t.i) for w in fr.split(" ")]
            elif len(t.text) <= 2 and t.text.isalpha() and t.text.islower():
                self.status[t.i] = "proper"
                items = [it(t.text, src=t.i)]
            else:
                self.status.setdefault(t.i, "unknown")
                items = [it(t.text, src=t.i, unk=True)]
        return self.mark(t, self.with_children(t, items, ctx))

    def with_children(self, t, head_items, ctx, skip_consumed=False, exclude=()):
        parts = [(t.i, head_items)]
        for c in t.children:
            if c.i in exclude:
                continue
            parts.append((c.i, self.render(c, self.child_ctx(t, c, ctx))))
        parts.sort(key=lambda p: p[0])
        return [x for _, items in parts for x in items]

    def child_ctx(self, head, c, ctx):
        d = {}
        if c.dep_ == "conj":
            d = {k: v for k, v in ctx.items() if k in ("role", "prep_en", "agree", "subj", "tense", "neg")}
        return d

    def render_pron(self, t, ctx):
        low = t.lower_
        self.status[t.i] = "grammar"
        role = ctx.get("role")
        if low in REL_WORDS:
            word = "qui" if t.dep_ in ("nsubj", "nsubjpass") or role == "pobj" else "que"
            return self.mark(t, [it(word, src=t.i)])
        if low == "whose":
            return self.mark(t, [it("dont", src=t.i)])
        if role == "pobj" or role == "attr":
            return self.mark(t, [it(STRESSED.get(low, low), src=t.i)])
        if low in SUBJ_PRON and t.dep_ in ("nsubj", "nsubjpass", "expl"):
            person, pl, g, w = SUBJ_PRON[low]
            if t.dep_ == "expl" or (ctx.get("impersonal") and low == "it"):
                w = "il"
            elif low in ("it", "they"):
                g = self.antecedent(pl)
                w = ("elles" if pl else "elle") if g == "f" else ("ils" if pl else "il")
            return self.mark(t, self.with_children(t, [it(w, src=t.i)], ctx))
        e = self.lookup(t, "PRON")
        w = e["fr"] if e else STRESSED.get(low, t.text)
        return self.mark(t, self.with_children(t, [it(x, src=t.i) for x in w.split(" ")], ctx))

    def render_one_of(self, t, ctx):
        prep = next(c for c in t.children if c.dep_ == "prep" and c.lower_ == "of")
        pobj = next((c for c in prep.children if c.dep_ == "pobj"), None)
        g = self.noun_info(pobj)["g"] if pobj is not None else "m"
        self.status[t.i] = "grammar"
        head = [it("la" if g == "f" else "le", "art", src=t.i), it("une" if g == "f" else "un", src=t.i)]
        return self.mark(t, self.with_children(t, head, ctx))

    def render_np(self, t, ctx):
        info = self.noun_info(t)
        role = ctx.get("role") or self.role_of(t)
        g, pl = info["g"], info["pl"]
        before, after_adj, after_cmp, superl, rest = [], [], [], [], []
        article = None
        quant = None
        poss_np = None
        quant_all = None
        children = [c for c in t.children]
        span = (self.over.get(t.i) or {}).get("span") or set()
        for j in span:
            if j != t.i:
                children += [c for c in self.sent.doc[j].children if c.i not in span]
        children.sort(key=lambda c: c.i)
        alls = [c for c in children if c.lower_ == "all" and c.dep_ in ("predet", "det", "nummod", "amod", "advmod")]
        dets = [c for c in children if c.dep_ in ("det", "predet") and c.i not in self.consumed and c not in alls]
        if alls:
            quant_all = alls[0]
            self.status[quant_all.i] = "grammar"
        for d in dets:
            low = d.lower_
            self.status[d.i] = "grammar"
            if low == "the":
                article = article or ("def", None)
            elif low in ("a", "an"):
                article = ("indef", None)
            elif low in ("this", "that", "these", "those"):
                article = ("dem", None)
            elif low in ("each", "every"):
                article = ("fixed", "chaque")
            elif low == "all":
                quant = ("all", None)
            elif low == "some":
                article = ("indef_or_part", None)
            elif low in ("no",):
                article = ("fixed", "aucune" if g == "f" else "aucun")
            elif low == "another":
                article = ("fixed", "une autre" if g == "f" else "un autre")
            elif low == "any":
                article = ("indef_or_part", None)
            elif low == "both":
                article = ("fixed", "les deux")
            else:
                e = self.lookup(d, "DET")
                article = ("fixed", e["fr"] if e else d.text)
        for c in children:
            if c.dep_ == "poss" and c.i not in self.consumed:
                if c.pos_ == "PRON" and c.lower_ in POSS_PRON:
                    self.status[c.i] = "grammar"
                    article = ("poss", POSS_PRON[c.lower_])
                else:
                    poss_np = c
                    article = article or ("def", None)
            if c.dep_ == "case":
                self.status[c.i] = "grammar"
        adjs = [c for c in children if c.dep_ in ("amod", "nmod") and c.pos_ in ("ADJ", "VERB") and c.i not in self.consumed]
        for a in list(adjs):
            if self.lemma(a) in QUANT_ADJ or a.lower_ in QUANT_ADJ:
                low = a.lower_
                self.status[a.i] = "grammar"
                adjs.remove(a)
                if low == "many":
                    quant = ("many", None)
                elif low == "several":
                    quant = ("fixed", "plusieurs")
                elif low == "few":
                    quant = ("fixed", "peu de")
                elif low in ("less", "fewer"):
                    quant = ("fixed", "moins de")
                elif low == "more" and not dets:
                    quant = ("fixed", "plus de")
                elif low == "most" and not dets:
                    quant = ("most", None)
                elif low == "much":
                    quant = ("fixed", "beaucoup de")
                elif low == "other":
                    before.append((a.i, [it("autres" if pl else "autre", src=a.i)]))
                    self.fr_of[a.i] = ["autres" if pl else "autre"]
        nums = [c for c in children if c.dep_ == "nummod" and c not in alls]
        if quant_all is not None:
            quant = ("all", [x for x in quant_all.children if x.dep_ == "advmod"])
        for a in adjs:
            entry = self.lookup(a, "ADJ")
            sup = a.tag_ == "JJS" or any(x.lower_ == "most" for x in a.children if x.dep_ == "advmod")
            items = self.render_adjp(a, {"agree": (g, pl), "attrib": True, "superl": sup})
            is_pre = bool(entry and entry["x"].get("pre"))
            if sup and not is_pre:
                superl.append((a.i, [it(F.definite(g, pl), "art", src=None)] + items))
            elif is_pre:
                if items:
                    items[0] = {**items[0], "preadj": True}
                before.append((a.i, items))
            else:
                after_adj.append((a.i, items))
        for c in children:
            if c.i in span:
                continue
            if c.dep_ == "compound" and c.i not in self.consumed:
                if c.pos_ == "PROPN" and t.pos_ == "PROPN":
                    before.append((c.i, self.render(c, {"role": "compound"})))
                elif not self.lookup(c, "NOUN") and self.lex.get(c.lower_, "ADJ", self.domain):
                    after_adj.append((c.i, self.render_adjp(c, {"agree": (g, pl), "attrib": True, "force_adj": True})))
                else:
                    ci = self.noun_info(c)
                    self.status.setdefault(c.i, "dict" if ci["known"] else "unknown")
                    sub = self.with_children(c, [it(ci["fr"], src=c.i, unk=not ci["known"])], {"role": "compound"})
                    after_cmp.append((c.i, [it("de", "prep", src=None)] + self.mark(c, sub)))
            elif c.dep_ == "compound":
                after_cmp.append((c.i, self.render(c, {})))
        handled = set(span) | {d.i for d in dets} | {c.i for c in alls} | {x.i for c in alls for x in c.children} \
            | {c.i for c in children if c.dep_ in ("poss", "case", "compound", "nummod")} \
            | {a.i for a in adjs} | {c.i for c in children if c.dep_ in ("amod",) and (self.lemma(c) in QUANT_ADJ or c.lower_ in QUANT_ADJ)}
        for c in children:
            if c.i in handled:
                continue
            if c.dep_ in ("amod", "nmod") and c.i in self.consumed:
                rest.append((c.i, self.render(c, {})))
                continue
            sub_ctx = {"role": role, "agree": (g, pl), "prep_en": ctx.get("prep_en"), "conj": True, "prep_fr": ctx.get("prep_fr"),
                       "gov_def": ctx.get("gov_def"),
                       "neg": ctx.get("neg")} if c.dep_ == "conj" else {"antecedent": (g, pl)}
            if c.dep_ in ("relcl", "acl"):
                sub_ctx = {"antecedent": (g, pl), "head_noun": t}
            if c.dep_ == "prep":
                sub_ctx = {**sub_ctx, "gov_def": bool(article and article[0] in ("def", "dem", "poss", "fixed")) or quant is not None}
            rest.append((c.i, self.render(c, sub_ctx)))
        head_words = [it(w, src=t.i, unk=not info["known"]) for w in info["fr"].split(" ")]
        num_items = []
        for nm in nums:
            num_items += self.render(nm, {})
        if not info["known"] and not dets and t.i not in self.over:
            ve = self.lookup(t, "VERB")
            if ve:
                self.status[t.i] = "rule"
                inf = ve["fr"]
                return self.mark(t, [it(w, src=t.i) for w in inf.split(" ")])
        art_items = self.article_items(t, info, role, ctx, article, quant, bool(adjs), bool(nums), poss_np)
        if ctx.get("conj") and ctx.get("prep_fr") in ("de", "à") and not info.get("proper") and \
                not (art_items and art_items[0]["t"] in ("de", "d'")):
            art_items = [it(ctx["prep_fr"], "prep")] + art_items
        before.sort(key=lambda p: p[0])
        out = art_items + num_items + [x for _, items in before for x in items] + head_words
        out += [x for _, items in sorted(after_cmp) for x in items]
        out += [x for _, items in sorted(after_adj) for x in items]
        out += [x for _, items in sorted(superl) for x in items]
        if poss_np is not None:
            out += [it("de", "prep")] + self.render(poss_np, {"role": "pobj", "prep_en": "of", "bare_ok": True})
        pre_rest = [x for i, items in sorted(rest) if i < t.i for x in items]
        post_rest = [x for i, items in sorted(rest) if i > t.i for x in items]
        out = pre_rest + out + post_rest
        self.fix_before_vowel(out)
        if role in ("subj", "obj") and not info.get("proper"):
            self.remember(t, info, role)
        elif info.get("proper") and role == "subj":
            self.remember(t, info, role)
        return self.mark(t, out)

    def role_of(self, t) -> str:
        d = t.dep_
        while d == "conj":
            t = t.head
            d = t.dep_
        if d in ("nsubj", "nsubjpass", "csubj"):
            return "subj"
        if d in ("dobj", "attr", "oprd"):
            return "obj" if d == "dobj" else "attr"
        if d == "pobj":
            return "pobj"
        if d == "dative":
            return "obj"
        if d == "appos":
            return "appos"
        if d == "npadvmod":
            return "adv"
        return d

    def article_items(self, t, info, role, ctx, article, quant, has_adj, has_num, poss_np):
        g, pl = info["g"], info["pl"]
        if info["x"].get("noart") or info["x"].get("city"):
            return []
        if info.get("proper") and not info["x"].get("country") and not article:
            return []
        if info.get("proper") and info["x"].get("country") and ctx.get("no_article"):
            return []
        neg = ctx.get("neg")
        if quant:
            q = quant[0]
            if q == "all":
                tout = ("toutes" if g == "f" else "tous") if pl else ("toute" if g == "f" else "tout")
                adv = [w for a in (quant[1] or []) for w in self.render(a, {})]
                if not article or article[0] == "def":
                    return adv + [it(tout), it(F.definite(g, pl), "art")]
                return adv + [it(tout)] + self.article_items(t, info, role, ctx, article, None, has_adj, has_num, poss_np)
            if q == "many":
                return [it("de"), it("nombreuses" if g == "f" else "nombreux")]
            if q == "most":
                return [it("la"), it("plupart"), it("de"), it("les", "art")]
            return [it(w) for w in quant[1].split(" ")]
        if article:
            kind, val = article
            if kind == "def":
                return [it(F.definite(g, pl), "art")]
            if kind == "indef":
                if neg and role == "obj":
                    return [it("de", "art")]
                return [it(F.indefinite(g, pl), "art")]
            if kind == "dem":
                return [it(F.demonstrative(g, pl, info["fr"]), "dem")]
            if kind == "poss":
                person, owner_pl = val
                return [it(F.possessive(person, owner_pl, g, pl, info["fr"]), "poss")]
            if kind == "indef_or_part":
                if neg:
                    return [it("de", "art")]
                return [it("des", "art")] if pl else [it(F.partitive(g), "art")]
            if kind == "fixed":
                return [it(w) for w in val.split(" ")]
        if has_num:
            return []
        if info.get("proper"):
            return [it(F.definite(g, pl), "art")]
        if role == "subj":
            return [it(F.definite(g, pl), "art")]
        if role in ("obj", "attr"):
            if pl:
                return [it("de" if neg else "des", "art")]
            if self.lemma(t) in PARTITIVE:
                return [it("de" if neg else F.partitive(g), "art")]
            return [it(F.definite(g, pl), "art")]
        if role == "pobj":
            prep = ctx.get("prep_en")
            if ctx.get("bare_ok"):
                return []
            if prep == "in" and not pl and not has_adj:
                return []
            if prep in ("into",):
                return []
            gov_def = ctx.get("gov_def")
            if prep == "of" and gov_def and not has_adj or prep == "of" and gov_def and not pl:
                return [it(F.definite(g, pl), "art")]
            if pl:
                return [it("les" if prep == "to" else "des", "art")]
            if has_adj and prep == "with":
                return [it(F.indefinite(g, pl), "art")]
            if prep in ("of", "by", "with", "without", "as", "per", "into"):
                return []
            return [it(F.definite(g, pl), "art")]
        if role in ("adv",):
            return []
        return [it("des", "art")] if pl else [it(F.definite(g, pl), "art")]

    def fix_before_vowel(self, items):
        for i in range(len(items) - 1):
            w, nxt = items[i], items[i + 1]["t"]
            if w.get("k") == "dem" and w["t"] == "ce" and F.starts_with_vowel(nxt):
                w["t"] = "cet"
            if w.get("k") == "poss" and w["t"] in ("ma", "ta", "sa") and F.starts_with_vowel(nxt):
                w["t"] = {"ma": "mon", "ta": "ton", "sa": "son"}[w["t"]]
            if w.get("mv") and F.starts_with_vowel(nxt):
                w["t"] = w["mv"]

    def render_adjp(self, a, ctx):
        g, pl = ctx.get("agree", ("m", False))
        o = self.over.get(a.i)
        if o and o["kind"] == "ADJ":
            form, entry, mv = o["fr"], None, None
            self.status[a.i] = "phrase"
        else:
            entry = self.lookup(a, "ADJ") if a.pos_ == "ADJ" or ctx.get("force_adj") else None
            if entry is None and ctx.get("force_adj"):
                entry = self.lex.get(a.lower_, "ADJ", self.domain)
            if entry is None and a.tag_ == "VBN":
                v = self.verb_entry(a)
                entry = {"fr": F.past_participle(F.split_verb(v["fr"])[1]), "x": {}, "derived": "pp"} if v else None
            if entry is None and a.tag_ == "VBG":
                v = self.verb_entry(a)
                entry = {"fr": F.present_participle(F.split_verb(v["fr"])[1]), "x": {"inv": True}, "derived": "ppr"} if v else None
            mv = None
            if entry:
                self.status.setdefault(a.i, "dict" if not entry.get("derived") else "rule")
                form = F.adj_form(entry["fr"], entry["x"], g, pl)
                mv = entry["x"].get("mv") if g == "m" and not pl else None
            else:
                self.status.setdefault(a.i, "unknown")
                form = a.text
        low = self.lemma(a)
        pre = []
        if a.tag_ == "JJR" and not any(c.lower_ in ("more", "less") for c in a.children):
            if low in ("good", "well"):
                form = F.adj_form("meilleur", {}, g, pl)
            elif low == "bad":
                form = "pire" + ("s" if pl else "")
            else:
                pre = [it("plus", src=a.i)]
        if a.tag_ == "JJS":
            if low == "good":
                form = F.adj_form("meilleur", {}, g, pl)
            elif low == "bad":
                form = "pire" + ("s" if pl else "")
            else:
                pre = [it("plus", src=a.i)]
            if not ctx.get("attrib"):
                pre = [it(F.definite(g, pl), "art")] + pre
        head = pre + [it(w, src=a.i, unk=not entry and not (o and o["kind"] == "ADJ"), **({"mv": mv} if mv else {}))
                      for w in form.split(" ")]
        parts = [(a.i, head)]
        for c in a.children:
            if c.i in self.consumed:
                parts.append((c.i, self.render(c, {})))
                continue
            if c.dep_ == "advmod":
                low_c = c.lower_
                if low_c == "most":
                    self.status[c.i] = "grammar"
                    w = [it("plus", src=c.i)] if ctx.get("attrib") else [it(F.definite(g, pl), "art"), it("plus", src=c.i)]
                    parts.append((c.i, self.mark(c, w)))
                    continue
                parts.append((c.i, self.render(c, {})))
            elif c.dep_ == "conj":
                parts.append((c.i, self.render(c, {"agree": (g, pl), "attrib": ctx.get("attrib")})))
            elif c.dep_ in ("xcomp",) and c.pos_ in ("VERB", "AUX"):
                prep = "de" if ctx.get("impersonal") else "à"
                parts.append((c.i, self.render(c, {"inf_prep": prep})))
            else:
                parts.append((c.i, self.render(c, {"agree": (g, pl)} if c.dep_ == "conj" else {})))
        parts.sort(key=lambda p: p[0])
        return self.mark(a, [x for _, items in parts for x in items])

    def prep_fr(self, p, pobj) -> tuple[str, dict]:
        low = p.lower_
        gov = p.head
        while p.dep_ == "conj" and gov.pos_ == "ADP":
            gov = gov.head
        if gov.i in self.phrase_head:
            gov = self.sent.doc[self.phrase_head[gov.i]]
        ctx = {}
        if p.i in self.fixed:
            return self.fixed[p.i], ctx
        o = self.over.get(gov.i)
        gx = (o or {}).get("x") or {}
        if gov.pos_ in ("VERB", "AUX"):
            ge = self.verb_entry(gov)
            if ge:
                gx = {**ge["x"], **gx}
        if low in gx and isinstance(gx[low], str):
            return gx[low], ctx
        if pobj is not None:
            pi = self.noun_info(pobj) if pobj.pos_ in ("NOUN", "PROPN") else None
            if low in ("in", "to") and pi and pi["x"].get("country"):
                ctx["no_article"] = True
                return ("en" if pi["g"] == "f" else "au"), ctx
            if low in ("in", "to") and pi and pi["x"].get("city"):
                return "à", ctx
            if low == "in" and pobj.like_num:
                return "en", ctx
            if low == "in" and pi and not pi["pl"] and not any(c.dep_ in ("det", "poss", "amod") for c in pobj.children) \
                    and not pi.get("proper"):
                return "en", ctx
            if low == "by" and (gov.pos_ in ("NOUN", "PROPN", "NUM") and (self.lemma(gov) in WORK_NOUNS or pobj.pos_ == "PROPN")):
                return "de", ctx
            if low == "for" and self.lemma(pobj) in TIME_NOUNS and (pi and pi["pl"] or pobj.lower_ == "time"):
                return "pendant", ctx
        if low == "by" and p.dep_ == "agent":
            return "par", ctx
        if low == "into":
            return "en", ctx
        if low == "about":
            return "sur", ctx
        e = self.lex.get(low, "ADP")
        return (e["fr"] if e else p.text), ctx

    def render_pp(self, p, ctx):
        pobj = next((c for c in p.children if c.dep_ in ("pobj",)), None)
        pcomp = next((c for c in p.children if c.dep_ == "pcomp"), None)
        fr, extra_ctx = self.prep_fr(p, pobj)
        self.status.setdefault(p.i, "dict")
        if p.i in self.consumed and p.i not in self.fixed:
            fr = ""
        low = p.lower_
        parts = []
        if pcomp is not None and pcomp.tag_ == "VBG":
            if low == "by":
                fr = "en"
            if low == "after":
                fr = "après"
            sub = self.render(pcomp, {"gerund_after": low})
            parts.append((pcomp.i, sub))
        head = [it(w, "prep", src=p.i) for w in fr.split(" ")] if fr else []
        for c in p.children:
            if pcomp is not None and c.i == pcomp.i and pcomp.tag_ == "VBG":
                continue
            if pobj is not None and c.i == pobj.i:
                parts.append((c.i, self.render(c, {"role": "pobj", "prep_en": low, "prep_fr": fr, "gov_def": ctx.get("gov_def"), **extra_ctx})))
            else:
                parts.append((c.i, self.render(c, {"role": "pobj", "prep_en": low} if c.dep_ == "pcomp" else {})))
        parts.sort(key=lambda x: x[0])
        out = head + [x for _, items in parts for x in items]
        return self.mark(p, out)

    def verb_entry(self, v):
        o = self.over.get(v.i)
        if o and o["kind"] == "VERB":
            return {"fr": o["fr"], "x": o["x"], "phrase": True}
        low = self.lemma(v)
        if low == "be":
            return {"fr": "être", "x": {}}
        if low == "have":
            return {"fr": "avoir", "x": {}}
        if low == "do":
            return {"fr": "faire", "x": {}}
        return self.lookup(v, "VERB")

    def tense_of(self, v, auxes):
        modal = next((a for a in auxes if a.tag_ == "MD"), None)
        passive = any(a.dep_ == "auxpass" for a in auxes) or v.dep_ == "nsubjpass"
        perfect = any(self.lemma(a) == "have" and a.dep_ == "aux" for a in auxes) and v.tag_ == "VBN" \
            or any(self.lemma(a) == "have" for a in auxes) and passive and any(a.lower_ == "been" for a in auxes)
        progressive = v.tag_ == "VBG" and any(self.lemma(a) == "be" and a.dep_ == "aux" for a in auxes)
        first = next((a for a in auxes if a.tag_ != "TO"), v)
        past = first.tag_ in ("VBD",) or (first is v and v.tag_ == "VBD")
        res = {"modal": None, "tense": "pres", "passive": passive}
        if modal is not None:
            m = MODALS.get(modal.lower_, (None, "pres"))
            res["modal"], res["tense"] = m
            return res
        if perfect:
            res["tense"] = "pqp" if past else "pc"
        elif progressive:
            res["tense"] = "impf" if past else "pres"
        elif past:
            res["tense"] = "impf" if self.lemma(v) in STATIVE and not passive else "pc"
        return res

    def render_clause(self, v, ctx):
        children = list(v.children)
        auxes = [c for c in children if c.dep_ in ("aux", "auxpass") and c.i < v.i]
        subj = next((c for c in children if c.dep_ in ("nsubj", "nsubjpass", "csubj", "expl")), None)
        expl = next((c for c in children if c.dep_ == "expl"), None)
        negs = [c for c in children if c.dep_ == "neg"]
        to_aux = next((a for a in auxes if a.tag_ == "TO"), None)
        for a in auxes + negs:
            self.status[a.i] = "grammar"
        entry = self.verb_entry(v)
        if entry:
            self.status.setdefault(v.i, "phrase" if entry.get("phrase") else "dict")
        else:
            self.status.setdefault(v.i, "unknown")
        vfr = entry["fr"] if entry else v.text
        vx = entry["x"] if entry else {}
        neg_word = "pas" if negs else None
        moved_adv, drop = [], set()
        for c in children:
            if c.dep_ in ("advmod", "neg") and c.lower_ in ("never",):
                neg_word, _ = "jamais", drop.add(c.i)
                self.status[c.i] = "grammar"
            if c.dep_ == "advmod" and c.lower_ in ("anymore", "longer") and negs:
                neg_word, _ = "plus", drop.add(c.i)
                self.status[c.i] = "grammar"
        if subj is not None:
            sf = self.subj_features(subj, v)
        elif ctx.get("subj"):
            sf = ctx["subj"]
        elif v.dep_ in ("relcl", "acl") and ctx.get("antecedent"):
            g, pl = ctx["antecedent"]
            sf = {"person": 3, "pl": pl, "g": g}
        else:
            sf = {"person": 3, "pl": False, "g": "m"}
        tinfo = self.tense_of(v, auxes)
        if ctx.get("tense") and not auxes and v.tag_ == ctx.get("tag"):
            tinfo = dict(ctx["tense"])
        refl = F.split_verb(vfr)[0]
        if tinfo["passive"] and (refl or vx.get("nopass")):
            tinfo["passive"] = False
        form_kind = "finite"
        if to_aux is not None or (v.tag_ == "VB" and not auxes and subj is None and v.dep_ in ("xcomp", "advcl", "ccomp", "csubj")):
            form_kind = "inf"
        elif v.tag_ == "VBG" and not auxes:
            form_kind = "ger" if v.dep_ in ("csubj", "pcomp", "pobj", "dobj") else "ppr"
        elif v.tag_ == "VBN" and not auxes and v.dep_ in ("acl", "amod", "advcl", "conj") and subj is None and \
                (v.dep_ != "conj" or ctx.get("pp_mode")):
            form_kind = "pp"
        clitics, clitic_ids = [], set()
        for c in children:
            if c.pos_ == "PRON" and c.lower_ in OBJ_CLITIC and c.dep_ in ("dobj", "dative", "iobj"):
                direct, indirect = OBJ_CLITIC[c.lower_]
                use_ind = c.dep_ in ("dative", "iobj") or vx.get("obj") == "à"
                w = indirect if use_ind else direct
                if c.lower_ == "it" and not use_ind:
                    w = "la" if self.antecedent(False, prefer_subject=False) == "f" else "le"
                clitics.append(w)
                clitic_ids.add(c.i)
                self.status[c.i] = "grammar"
                self.fr_of[c.i] = [w]
        raised = {}
        for c in children:
            if c.dep_ in ("ccomp", "xcomp") and c.pos_ in ("VERB", "AUX") and \
                    any(x.dep_ == "aux" and x.tag_ == "TO" for x in c.children):
                s2 = next((x for x in c.children if x.dep_ == "nsubj"), None)
                if s2 is not None:
                    raised[c.i] = s2
                    if s2.pos_ == "PRON" and s2.lower_ in OBJ_CLITIC:
                        direct, indirect = OBJ_CLITIC[s2.lower_]
                        clitics.append(indirect if vx.get("obj") == "à" else direct)
                        self.status[s2.i] = "grammar"
                        self.fr_of[s2.i] = [clitics[-1]]
            if c.dep_ == "ccomp" and c.pos_ == "NOUN":
                s2 = next((x for x in c.children if x.dep_ == "nsubj" and x.pos_ == "PRON"), None)
                if s2 is not None and s2.lower_ in OBJ_CLITIC:
                    self.skip.add(s2.i)
                    clitics.append(OBJ_CLITIC[s2.lower_][1])
                    self.status[s2.i] = "grammar"
                    self.fr_of[s2.i] = [clitics[-1]]
                    raised[c.i] = s2
        left_bound = subj.i if subj is not None else (auxes[0].i if auxes else v.i)
        for c in children:
            if c.dep_ == "advmod" and c.i not in drop and c.i not in self.consumed and c.i < v.i and \
                    c.i > left_bound and c.pos_ == "ADV":
                moved_adv.append(c)
        group = self.verb_group(vfr, vx, tinfo, sf, form_kind, neg_word, clitics,
                                [self.render(c, {}) for c in moved_adv], v, ctx)
        for c in moved_adv:
            drop.add(c.i)
        vg = [it(w, src=v.i, unk=not entry and i == len(group) - 1) for i, w in enumerate(group)]
        if ctx.get("inf_prep") and form_kind == "inf":
            vg = [it(ctx["inf_prep"], "prep")] + vg
        elif form_kind == "inf" and v.dep_ == "advcl" and not any(c.dep_ == "mark" for c in children):
            vg = [it("pour", "prep")] + vg
        if expl is not None and self.lemma(v) == "be" and expl.lower_ == "there":
            self.status[expl.i] = "grammar"
            av = F.finite("avoir", tinfo["tense"] if tinfo["tense"] in ("pres", "impf", "fut", "cond") else "pres", 3, False)
            vg = [it("il", src=expl.i), it("y")] + ([it("n'"), ] if neg_word else []) + [it(av, src=v.i)] + \
                ([it(neg_word)] if neg_word else [])
            subj = None
            drop.add(expl.i)
        parts = [(v.i, vg)]
        impersonal = subj is not None and subj.lower_ == "it" and any(
            x.dep_ == "xcomp" and x.pos_ in ("VERB", "AUX") for c in children if c.dep_ in ("acomp", "xcomp", "attr")
            for x in [c] + list(c.children))
        if subj is not None and subj.i not in drop and not ctx.get("skip_subj"):
            s_ctx = {"role": "subj", "impersonal": impersonal}
            if subj.dep_ == "csubj":
                s_ctx = {}
            if ctx.get("subj_prefix"):
                if subj.pos_ == "PRON" and subj.lower_ in OBJ_CLITIC:
                    pass
                else:
                    parts.append((subj.i, [it(ctx["subj_prefix"], "prep")] + self.render(subj, {"role": "pobj", "bare_ok": False, "prep_en": "to"})))
            else:
                parts.append((subj.i, self.render(subj, s_ctx)))
        has_xcomp = any(c.dep_ == "xcomp" for c in children)
        for c in children:
            if c.i in drop or c.i in clitic_ids or (subj is not None and c.i == subj.i) or c.i in {a.i for a in auxes} \
                    or c.i in {n.i for n in negs} or (expl is not None and c.i == expl.i):
                continue
            if c.dep_ == "prt" and c.i not in self.fixed:
                self.status[c.i] = "grammar" if c.i not in self.status else self.status[c.i]
                continue
            cctx = {}
            if c.dep_ == "dobj" and vx.get("dobj"):
                parts.append((c.i, [it(vx["dobj"], "prep")] + self.render(c, {"role": "pobj", "prep_en": "to", "prep_fr": vx["dobj"]})))
                continue
            if c.dep_ in ("dobj",):
                cctx = {"role": "obj", "neg": bool(neg_word)}
                if vx.get("obj") == "à" and has_xcomp:
                    parts.append((c.i, [it("à", "prep")] + self.render(c, {"role": "pobj", "bare_ok": True})))
                    continue
            elif c.dep_ == "dative":
                parts.append((c.i, [it("à", "prep")] + self.render(c, {"role": "pobj", "bare_ok": True})))
                continue
            elif c.dep_ in ("attr", "oprd"):
                cctx = {"role": "attr", "agree": (sf["g"], sf["pl"])}
            elif c.dep_ == "acomp":
                cctx = {"agree": (sf["g"], sf["pl"]), "impersonal": impersonal}
            elif c.dep_ == "dobj" and vx.get("dobj"):
                parts.append((c.i, [it(vx["dobj"], "prep")] + self.render(c, {"role": "pobj", "prep_en": "to"})))
                continue
            elif c.i in raised:
                if c.pos_ == "NOUN":
                    cctx = {"role": "obj"}
                else:
                    s2 = raised[c.i]
                    cctx = {"inf_prep": vx.get("inf") or "de", "subj_prefix": "à" if vx.get("obj") == "à" else None,
                            "skip_subj": s2.pos_ == "PRON"}
                    if s2.pos_ != "PRON" and vx.get("obj") != "à":
                        cctx["subj_prefix"] = None
            elif c.dep_ == "xcomp":
                if c.pos_ in ("ADJ",):
                    cctx = {"agree": (sf["g"], sf["pl"])}
                elif c.pos_ in ("NOUN", "PROPN"):
                    cctx = {"role": "attr"}
                else:
                    prep = vx.get("inf")
                    if self.lemma(v) == "be" and not tinfo["passive"]:
                        prep = "de"
                    cctx = {"inf_prep": prep, "subj": sf}
            elif c.dep_ == "ccomp":
                cctx = {}
                if c.i > v.i and not any(x.dep_ == "mark" for x in c.children) and c.pos_ in ("VERB", "AUX") and \
                        not any(x.tag_ in ("WDT", "WP", "WRB") for x in c.subtree):
                    parts.append((c.left_edge.i - 0.5, [it("que")]))
            elif c.dep_ == "conj" and c.pos_ in ("VERB", "AUX"):
                has_own_subj = any(x.dep_ in ("nsubj", "nsubjpass", "expl") for x in c.children)
                cctx = {} if has_own_subj else {"subj": sf, "pp_mode": form_kind == "pp"}
                if form_kind == "inf" and not has_own_subj:
                    cctx["inf_prep"] = None
            elif c.dep_ in ("relcl",):
                cctx = {"antecedent": (sf["g"], sf["pl"])}
            parts.append((c.i, self.render(c, cctx)))
        if v.dep_ == "relcl" and subj is not None and not any(c.dep_ == "dobj" for c in children) and \
                not any(x.lower_ in REL_WORDS | {"where", "whose", "when", "why"} for x in v.subtree if x.i < v.i):
            parts.append((v.left_edge.i - 0.5, [it("que")]))
        parts.sort(key=lambda p: p[0])
        out = [x for _, items in parts for x in items]
        return self.mark(v, out)

    def verb_group(self, vfr, vx, tinfo, sf, form_kind, neg, clitics, adv_items, v, ctx) -> list[str]:
        person, pl, g = sf["person"], sf["pl"], sf["g"]
        refl, inf, rest = F.split_verb(vfr)
        adv = [x["t"] for items in adv_items for x in items]
        restw = [rest] if rest else []
        agree_rest = vx.get("agree") or inf == "être" and rest in ("constitué", "composé")
        if agree_rest and rest:
            restw = [F.past_participle_agree(rest, g, pl)]
        refl_w = [F.REFLEXIVE[(person, pl)]] if refl else []
        if form_kind == "inf":
            core = ([("ne"), neg] if neg else []) + refl_w + clitics
            if tinfo["passive"]:
                return core + ["être", F.past_participle_agree(F.past_participle(inf), g, pl)] + restw + adv
            return core + [inf] + adv + restw
        if form_kind in ("ppr", "ger"):
            if form_kind == "ger" or ctx.get("gerund_after") in ("for", "without", "before", "of", "about", "in"):
                if ctx.get("gerund_after") == "after":
                    aux = "être" if F.uses_etre(inf, refl) else "avoir"
                    return [aux] + refl_w + clitics + [F.past_participle(inf)] + restw
                return ([("ne"), neg] if neg else []) + refl_w + clitics + [inf] + adv + restw
            return ([("ne")] if neg else []) + refl_w + clitics + [F.present_participle(inf)] + \
                ([neg] if neg else []) + adv + restw
        if form_kind == "pp":
            gg, pp_pl = ctx.get("antecedent", (g, pl))
            return [F.past_participle_agree(F.past_participle(inf), gg, pp_pl)] + adv + restw
        tense, modal, passive = tinfo["tense"], tinfo["modal"], tinfo["passive"]
        pre = (["ne"] if neg else []) + refl_w + clitics
        negw = [neg] if neg else []
        if modal:
            fin = F.finite(modal, tense, person, pl)
            tail = (["être", F.past_participle_agree(F.past_participle(inf), g, pl)] if passive else [inf]) + restw
            if refl:
                pre = (["ne"] if neg else []) + clitics
                tail = [F.REFLEXIVE[(person, pl)]] + tail
            return pre + [fin] + negw + adv + tail
        if passive:
            if tense in ("pc", "pqp"):
                fin = F.finite("avoir", "pres" if tense == "pc" else "impf", person, pl)
                return pre + [fin] + negw + adv + ["été", F.past_participle_agree(F.past_participle(inf), g, pl)] + restw
            fin = F.finite("être", tense, person, pl)
            return pre + [fin] + negw + adv + [F.past_participle_agree(F.past_participle(inf), g, pl)] + restw
        if tense in ("pc", "pqp"):
            aux = "être" if F.uses_etre(inf, refl) else "avoir"
            fin = F.finite(aux, "pres" if tense == "pc" else "impf", person, pl)
            pp = F.past_participle(inf)
            if aux == "être":
                pp = F.past_participle_agree(pp, g, pl)
            return pre + [fin] + negw + adv + [pp] + restw
        fin = F.finite(inf, tense, person, pl)
        return pre + [fin] + negw + adv + restw

    def translate(self) -> list[dict]:
        root = self.sent.root
        items = self.render(root, {})
        return items


def kind_plural(fr: str, x: dict) -> bool:
    return not x.get("noart") or True


def adverb_from_adj(a: dict) -> str:
    m = a["fr"].split(" ")[-1]
    if m.endswith("ant"):
        return m[:-3] + "amment"
    if m.endswith("ent"):
        return m[:-3] + "emment"
    if m[-1] in "aeiouéi" and not m.endswith("e"):
        return m + "ment"
    fem = a["x"].get("f") or F.adj_feminine(m)
    return fem + "ment"


class Translator:
    def __init__(self, nlp, lex: Lexicon):
        self.nlp, self.lex = nlp, lex
        self.memory: list[dict] = []
        self.names_like = {"hugo", "smith", "will", "hope", "rose", "grace", "victor", "winston", "julia"}
        self.female_names = {"cosette", "fantine", "ophelia", "julia", "juliet", "emma", "anna", "mary", "elizabeth",
                             "jane", "catherine", "marie", "virginia", "queen", "she"}

    def recase_heading(self, text: str) -> str:
        words = text.split(" ")
        out = []
        for w in words:
            low = w.lower()
            known = any((low, p) in self.lex.entries for p in ("NOUN", "ADJ", "VERB", "ADP", "DET", "CCONJ", "ADV")) or \
                any(low.rstrip("s") == k[0] for k in [(low.rstrip("s"),)] if (low.rstrip("s"), "NOUN") in self.lex.entries)
            proper = (low, "PROPN") in self.lex.entries
            out.append(low if known and not proper else w)
        return " ".join(out)

    @staticmethod
    def is_heading(par: str) -> bool:
        return len(par.split()) <= 10 and not re.search(r"[.!?:;]\s*$", par.strip())

    def detect_domain(self, docs) -> tuple[str | None, dict]:
        lemmas = [(LEMMA_ALIASES.get(t.lemma_.lower(), t.lemma_.lower()), t.pos_) for d in docs for t in d if t.is_alpha]
        votes = self.lex.domain_votes(lemmas)
        if votes["cs"] == votes["lit"]:
            return None, votes
        return ("cs" if votes["cs"] > votes["lit"] else "lit"), votes

    def translate(self, text: str, mode: str = "transfer", domain: str | None = "auto") -> dict:
        t0 = time.perf_counter()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip()) if p.strip()]
        paragraphs = [re.sub(r"\s*\n\s*", " ", p) for p in paragraphs]
        prepared = [("The " + self.recase_heading(p) if self.is_heading(p) else p, self.is_heading(p)) for p in paragraphs]
        docs = [self.nlp(p) for p, _ in prepared]
        t1 = time.perf_counter()
        dom_votes = None
        if domain == "auto":
            domain, dom_votes = self.detect_domain(docs)
        self.memory = []
        out_pars, freq, sent_list = [], {}, []
        stats = Counter()
        t_transfer = 0.0
        t_synth = 0.0
        for (ptxt, heading), doc in zip(prepared, docs):
            par_sents = []
            for sent in doc.sents:
                a = time.perf_counter()
                r = Realizer(self, sent, domain)
                if heading:
                    r.consumed.add(sent.start)
                    r.status[sent.start] = "skip"
                if mode == "direct":
                    items = self.direct(r, sent)
                else:
                    items = r.translate()
                if heading:
                    items = [x for x in items if x.get("src") != sent.start and not (x.get("k") == "art" and x is items[0])]
                b = time.perf_counter()
                fr = F.finalize(items)
                fr = capitalize_first(fr)
                if heading:
                    fr = fr.rstrip(".")
                c = time.perf_counter()
                t_transfer += b - a
                t_synth += c - b
                toks = []
                for tok in sent:
                    if tok.is_space or (heading and tok.i == sent.start):
                        continue
                    st = r.status.get(tok.i, "unknown" if not tok.is_punct else "punct")
                    if tok.is_punct:
                        st = "punct"
                    elif st == "unknown" and r.fr_of.get(tok.i) and not any(
                            x.get("unk") for x in items if x.get("src") == tok.i):
                        st = "dict"
                    toks.append({"i": tok.i - sent.start, "text": tok.text, "lemma": tok.lemma_, "pos": tok.pos_,
                                 "pos_ru": POS_RU.get(tok.pos_, tok.pos_), "tag": tok.tag_,
                                 "tag_ru": TAG_RU.get(tok.tag_, tok.tag_), "dep": tok.dep_, "role": role_of(tok),
                                 "morph": morph_ru(tok), "head": tok.head.i - sent.start, "head_text": tok.head.text,
                                 "fr": " ".join(r.fr_of.get(tok.i, [])), "status": st})
                    if not tok.is_punct:
                        stats["words"] += 1
                        stats[st] += 1
                        key = (r.lemma(tok), tok.pos_)
                        if key not in freq:
                            freq[key] = LexemeEntry(key[0], tok.pos_)
                            freq[key].translation = self.lemma_translation(r, tok)
                        freq[key].add_from_token(tok, sent.text)
                unknown = [x["text"] for x in toks if x["status"] == "unknown"]
                skip = {sent.start} if heading else set()
                const = syntax.constituency_tree(sent, skip)
                sd = {"en": sent.text[4:] if heading else sent.text, "fr": fr, "tokens": toks, "unknown": unknown,
                      "heading": heading, "html": self.html(items),
                      "dep_tree": syntax.dependency_tree(sent, r.fr_of, skip), "const_tree": const,
                      "bracket": syntax.bracketed(const)}
                par_sents.append(sd)
                sent_list.append(sd)
            out_pars.append({"heading": heading, "sentences": par_sents,
                             "fr": " ".join(s["fr"] for s in par_sents)})
        total = (time.perf_counter() - t0) * 1000
        words = stats["words"]
        translated = stats["dict"] + stats["phrase"] + stats["grammar"] + stats["rule"]
        freq_list = sorted((e.to_dict() for e in freq.values()), key=lambda d: (-d["frequency"], d["lemma"]))
        return {
            "mode": mode, "domain": domain, "domain_votes": dom_votes,
            "text": "\n\n".join(p["fr"] for p in out_pars),
            "paragraphs": out_pars, "sentences": sent_list,
            "stats": {"words": words, "translated": translated, "unknown": stats["unknown"],
                      "proper": stats["proper"], "by_dict": stats["dict"], "by_phrase": stats["phrase"],
                      "by_grammar": stats["grammar"], "by_rule": stats["rule"],
                      "sentences": len(sent_list), "unique": len(freq_list),
                      "coverage": round(100 * (translated + stats["proper"]) / words, 1) if words else 0.0},
            "freq": freq_list,
            "time_ms": {"analysis": (t1 - t0) * 1000, "transfer": t_transfer * 1000,
                        "synthesis": t_synth * 1000, "total": total},
        }

    def lemma_translation(self, r: Realizer, tok) -> dict | None:
        if tok.is_punct:
            return None
        if tok.i in r.over and r.over[tok.i]["kind"] != "FIX":
            o = r.over[tok.i]
            return {"fr": o["fr"], "gender": o.get("gender"), "source": "оборот"}
        pos = tok.pos_ if tok.pos_ != "AUX" else "VERB"
        e = r.lookup(tok, pos)
        if not e and pos == "PROPN":
            e = r.lex.get(tok.lower_, "NOUN")
        if not e:
            return None
        info = {"fr": e["fr"], "gender": e.get("gender"), "source": "словарь" if not e.get("derived") else "правило"}
        if pos in ("NOUN",) and e.get("gender"):
            info["plural"] = F.noun_plural(e["fr"], e["x"].get("pl"))
        if pos == "ADJ":
            info["forms"] = [F.adj_form(e["fr"], e["x"], g, p) for g, p in (("m", False), ("f", False), ("m", True), ("f", True))]
        if pos == "VERB":
            refl, inf, rest = F.split_verb(e["fr"])
            info["forms"] = F.present_forms(inf)
            info["pp"] = F.past_participle(inf)
        return info

    def direct(self, r: Realizer, sent) -> list[dict]:
        out = []
        for t in sent:
            if t.i in r.consumed:
                if t.i in r.fixed and r.fixed[t.i]:
                    out.append(it(r.fixed[t.i], src=t.i))
                continue
            if t.is_punct:
                r.status[t.i] = "punct"
                out.append(it(PUNCT_MAP.get(t.text, t.text), "punct", src=t.i))
                continue
            o = r.over.get(t.i)
            if o:
                fr = o["fr"]
            elif t.pos_ == "DET" and t.lower_ in ("the",):
                fr = "le"
                r.status[t.i] = "grammar"
            elif t.pos_ == "PART" and t.lower_ == "to":
                fr = ""
                r.status[t.i] = "grammar"
            elif t.pos_ == "PART" and t.lower_ in ("not", "n't"):
                fr = "pas"
                r.status[t.i] = "grammar"
            elif t.pos_ in ("AUX",) and t.dep_ in ("aux", "auxpass"):
                e = r.verb_entry(t)
                fr = e["fr"] if e else t.text
                r.status[t.i] = "grammar"
            else:
                pos = "VERB" if t.pos_ == "AUX" else t.pos_
                e = r.verb_entry(t) if pos == "VERB" else (r.lookup(t, pos) or (r.lex.get(t.lower_, "PROPN") if pos == "PROPN" else None))
                if e:
                    fr = e["fr"]
                    r.status.setdefault(t.i, "dict")
                    if pos == "NOUN" and t.tag_ == "NNS":
                        fr = F.noun_plural(fr, e["x"].get("pl"))
                elif t.pos_ == "PROPN" or t.like_num:
                    fr = t.text
                    r.status[t.i] = "proper"
                else:
                    fr = t.text
                    r.status[t.i] = "unknown"
            if fr:
                r.fr_of[t.i] = [fr]
                out.append(it(fr, src=t.i, unk=r.status.get(t.i) == "unknown"))
        return out

    @staticmethod
    def html(items) -> str:
        import html as H
        s = F.finalize(items)
        unk = {x["t"] for x in items if x.get("unk")}
        res = H.escape(capitalize_first(s))
        for w in sorted(unk, key=len, reverse=True):
            if w:
                res = re.sub(rf"(?<![\w>]){re.escape(H.escape(w))}(?![\w<])", f"<mark>{H.escape(w)}</mark>", res)
        return res


def capitalize_first(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
        if ch.isdigit():
            return s
    return s
