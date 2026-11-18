"""Агент семантического реферирования на основе базы знаний OSTIS.

В отличие от метода sentence extraction, который оценивает предложения по
частотам слов, агент работает с понятиями базы знаний:

1. Семантическая индексация. Из sc-памяти выбираются понятия предметных
   областей и их идентификаторы на языке документа (nrel_main_idtf, nrel_idtf);
   идентификаторы приводятся к последовательностям основ. В каждом предложении
   находятся упоминания понятий (самое длинное совпадение последовательности
   основ), так текст отображается на понятия базы знаний.
2. Начальная значимость понятия
       a0(c) = 0,5·(1 + tf(c,D)/tf_max(D)) · spec(c),
   где tf(c,D) — число упоминаний понятия, spec(c) = h/(h+1) — специфичность,
   h — глубина понятия в иерархии nrel_inclusion (корневые понятия вроде
   «информатика» или «литература» неинформативны, spec = 0).
3. Распространение активации по семантической сети: понятие получает часть
   значимости соседей — родителя, дочерних и связанных понятий (nrel_inclusion,
   nrel_related):  a(c) = a0(c) + α · Σ_{n ∈ N(c)} a0(n),  α = 0,2.
   Так «tri rapide» и «tri fusion» усиливают «tri», а «Jean Valjean» — «misère».
4. Отбор предложений с покрытием понятий: N раз выбирается предложение
   с наибольшим приростом  gain(S) = Σ_{c∈C(S)\\K} a(c) + β·Σ_{c∈C(S)∩K} a(c),
   где K — понятия, уже покрытые рефератом, β = 0,3 (повторы штрафуются).
   Выбранные предложения выводятся в порядке следования в тексте.
5. Реферат в виде ключевых слов — ключевые понятия базы знаний: понятия
   с наибольшей активацией, сгруппированные по иерархии онтологии
   (дочерние понятия выводятся под родительским).
"""
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from sc_memory import ScMemory
from summarizer import build_document
from text_processor import WORD_RE, terms

KB_DIR = Path(__file__).resolve().parent / "kb"
DOMAIN_STRUCTS = {"subject_domain_computer_science": "cs", "subject_domain_literature": "lit"}
ALPHA, BETA = 0.2, 0.3


class SemanticAgent:
    def __init__(self, kb_dir: Path = KB_DIR):
        t0 = time.perf_counter()
        # параметры метода (меняются только при исследовании вклада шагов алгоритма)
        self.alpha, self.beta, self.use_domain, self.use_spec = ALPHA, BETA, True, True
        self.memory = ScMemory()
        self.files = self.memory.load_dir(kb_dir)
        m = self.memory
        self.concepts = {}                  # адрес понятия → сведения
        for sd, dom in DOMAIN_STRUCTS.items():
            for c in m.members(sd):
                self.concepts[c] = {"id": m.idtf_of(c), "domain": dom,
                                    "ru": (m.identifiers(c, "ru") or [m.idtf_of(c)])[0]}
        for c in self.concepts:
            parents = [p for p in m.related(c, "nrel_inclusion", "in") if p in self.concepts]
            self.concepts[c]["parent"] = parents[0] if parents else None
            rel = set(m.related(c, "nrel_related", "out")) | set(m.related(c, "nrel_related", "in"))
            children = set(m.related(c, "nrel_inclusion", "out"))
            nb = (set(parents) | children | rel) & set(self.concepts)
            self.concepts[c]["neighbors"] = sorted(nb)
        for c in self.concepts:
            h, p = 0, self.concepts[c]["parent"]
            while p is not None and h < 20:
                h, p = h + 1, self.concepts[p]["parent"]
            self.concepts[c]["depth"] = h
            self.concepts[c]["spec"] = h / (h + 1)
        self.load_ms = (time.perf_counter() - t0) * 1000

    @lru_cache(maxsize=4)
    def lexicon(self, lang: str) -> dict:
        """Последовательность основ → [(понятие, словоформа)] для языка lang.

        Для однословных идентификаторов запоминается словоформа: стеммер сводит
        к одной основе разные слова (ordine / ordinamento), поэтому одно слово
        сопоставляется с понятием, только если совпадает и основа, и начало
        словоформы. Идентификатор, который после удаления стоп-слов сократился
        до одного слова («nombre premier» → «nombre»), не используется."""
        lex = defaultdict(list)
        for c in self.concepts:
            for idtf in self.memory.identifiers(c, lang):
                pairs = terms(idtf, lang)
                key = tuple(s for s, _ in pairs)
                content = [w for w in WORD_RE.findall(idtf.lower()) if len(w) > 3]
                if not key or (len(key) == 1 and len(content) > 1):
                    continue
                lex[key].append((c, pairs[0][1] if len(key) == 1 else None))
        return dict(lex)

    def find_concepts(self, pairs: list[tuple[str, str]], lang: str, allowed=None) -> list[tuple[int, tuple]]:
        """Упоминания понятий в последовательности (основа, словоформа): жадное самое длинное совпадение."""
        lex = self.lexicon(lang)
        max_len = max((len(k) for k in lex), default=1)
        stems = [s for s, _ in pairs]
        found, i = [], 0
        while i < len(stems):
            for L in range(min(max_len, len(stems) - i), 0, -1):
                key = tuple(stems[i:i + L])
                hits = [c for c, form in lex.get(key, [])
                        if (allowed is None or c in allowed)
                        and (form is None or pairs[i][1].startswith(form[:max(len(form) - 1, 3)]))]
                if hits:
                    found += [(c, key) for c in hits]
                    i += L
                    break
            else:
                i += 1
        return found

    def name(self, c: int, lang: str) -> str:
        ids = self.memory.identifiers(c, lang, rels=("nrel_main_idtf",))
        return ids[0] if ids else self.concepts[c]["ru"]

    def summarize(self, paragraphs: list[str], lang: str, n_sentences: int = 10, n_keywords: int = 10) -> dict:
        t0 = time.perf_counter()
        doc = build_document(paragraphs, lang)
        sents = doc["sentences"]
        pairs = [terms(s["text"], lang) for s in sents]
        # 1) определение предметной области по базе знаний: какой области понятия упоминаются чаще
        dom_votes = Counter()
        for pr in pairs:
            for c, _ in self.find_concepts(pr, lang):
                dom_votes[self.concepts[c]["domain"]] += 1
        domain = dom_votes.most_common(1)[0][0] if dom_votes else None
        allowed = ({c for c, v in self.concepts.items() if v["domain"] == domain} if self.use_domain
                   else set(self.concepts))
        # 2) семантическая индексация предложений понятиями этой предметной области
        tf, matched = Counter(), defaultdict(set)
        for s, pr in zip(sents, pairs):
            occ = self.find_concepts(pr, lang, allowed)
            s["concepts"] = sorted({c for c, _ in occ})
            for c, key in occ:
                tf[c] += 1
                matched[c].update(key)
        tf_max = max(tf.values(), default=1)
        a0 = {c: 0.5 * (1 + f / tf_max) * (self.concepts[c]["spec"] if self.use_spec else 1.0) for c, f in tf.items()}
        act = defaultdict(float)
        for c, v in a0.items():
            act[c] += v
            for n in self.concepts[c]["neighbors"]:
                if n in allowed:
                    act[n] += self.alpha * v
        # семантический вес предложения (для таблицы) и отбор с покрытием понятий
        for s in sents:
            s["sem_weight"] = sum(act[c] for c in s["concepts"])
        covered, chosen = set(), []
        remaining = list(range(len(sents)))
        for _ in range(min(n_sentences, len(sents))):
            best, best_gain = None, -1.0
            for i in remaining:
                cs = sents[i]["concepts"]
                gain = sum(act[c] for c in cs if c not in covered) + self.beta * sum(act[c] for c in cs if c in covered)
                if gain > best_gain + 1e-12:
                    best, best_gain = i, gain
            chosen.append(best)
            remaining.remove(best)
            sents[best]["gain"] = best_gain
            covered.update(sents[best]["concepts"])
        chosen.sort()
        for s in sents:
            s["in_summary"] = s["idx"] in chosen
        keywords = self._concept_tree(act, tf, matched, lang, n_keywords)
        concepts = sorted(({"concept": self.concepts[c]["id"], "name": self.name(c, lang), "ru": self.concepts[c]["ru"],
                            "domain": self.concepts[c]["domain"], "tf": tf.get(c, 0), "a0": round(a0.get(c, 0), 4),
                            "activation": round(v, 4),
                            "parent": self.concepts[self.concepts[c]["parent"]]["id"] if self.concepts[c]["parent"] else None}
                           for c, v in act.items() if v > 0), key=lambda x: (-x["activation"], x["concept"]))
        return {"doc": doc, "sentences": sents, "summary_idx": chosen, "keywords": keywords, "concepts": concepts,
                "domain_votes": dict(dom_votes), "domain": domain, "time_ms": (time.perf_counter() - t0) * 1000}

    def _concept_tree(self, act, tf, matched, lang, k):
        """Ключевые понятия, сгруппированные по иерархии онтологии (только упомянутые в тексте)."""
        ranked = sorted((c for c in tf if act[c] > 0), key=lambda c: (-act[c], -tf[c], self.concepts[c]["id"]))
        top, children = [], defaultdict(list)
        for c in ranked:
            p = self.concepts[c]["parent"]
            if p in top and len(children[p]) < 4:
                children[p].append(c)
            elif len(top) < k:
                top.append(c)
        return [{"concept": self.concepts[c]["id"], "term": self.name(c, lang), "ru": self.concepts[c]["ru"],
                 "stem": next(iter(matched[c])), "stems": sorted(matched[c]), "weight": round(act[c], 4), "tf": tf[c],
                 "children": [{"concept": self.concepts[x]["id"], "phrase": self.name(x, lang), "ru": self.concepts[x]["ru"],
                               "count": tf[x], "weight": round(act[x], 4)} for x in children[c]]}
                for c in top]

    def stats(self) -> dict:
        dom = Counter(v["domain"] for v in self.concepts.values())
        n_incl = sum(1 for v in self.concepts.values() if v["parent"] is not None)
        n_rel = sum(len(self.memory.related(c, "nrel_related")) for c in self.concepts)
        return {"files": self.files, "memory": self.memory.stats(), "concepts": len(self.concepts),
                "by_domain": dict(dom), "inclusion": n_incl, "related": n_rel,
                "identifiers": {lang: sum(len(self.memory.identifiers(c, lang)) for c in self.concepts)
                                for lang in ("fr", "it")}, "load_ms": self.load_ms}
