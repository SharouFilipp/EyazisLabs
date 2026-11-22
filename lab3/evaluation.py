import random
import re
import statistics
from collections import Counter

from summarizer import select_sentences, weigh_sentences
from text_processor import terms

VARIANTS = {
    "ostis": "семантический метод OSTIS (агент по базе знаний)",
    "full": "sentence extraction: Score·Posd·Posp",
    "score": "только Score (без позиционных функций)",
    "score_posd": "Score·Posd",
    "score_posp": "Score·Posp",
    "lead": "Lead-N (первые N предложений)",
    "random": "Random-N (случайные N предложений)",
}


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def match_reference(sentences: list[str], reference: list[str]) -> set:
    ref = {_norm(r) for r in reference}
    return {i for i, s in enumerate(sentences) if _norm(s) in ref}


def prf(selected: set, relevant: set) -> tuple[float, float, float]:
    tp = len(selected & relevant)
    p = tp / len(selected) if selected else 0.0
    r = tp / len(relevant) if relevant else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def rouge_n(candidate: str, reference: str, lang: str, n: int) -> float:
    def grams(text):
        st = [s for s, _ in terms(text, lang)]
        return Counter(tuple(st[i:i + n]) for i in range(len(st) - n + 1))
    c, r = grams(candidate), grams(reference)
    overlap = sum((c & r).values())
    if not overlap:
        return 0.0
    p, rec = overlap / sum(c.values()), overlap / sum(r.values())
    return 2 * p * rec / (p + rec)


def keyword_scores(keywords: list[dict], reference_kw: list[str], lang: str) -> tuple[float, float]:
    ref_stems = [{s for s, _ in terms(k, lang)} for k in reference_kw]
    def stems_of(kw):
        return kw.get("stems") or [kw["stem"]]
    ok = [kw for kw in keywords if any(st in rs for rs in ref_stems for st in stems_of(kw))]
    precision = len(ok) / len(keywords) if keywords else 0.0
    covered = 0
    for rs in ref_stems:
        cand = {st for kw in keywords for st in stems_of(kw)}
        for kw in keywords:
            for ch in kw.get("children", []):
                cand |= {s for s, _ in terms(ch["phrase"], lang)}
        if rs & cand:
            covered += 1
    recall = covered / len(ref_stems) if ref_stems else 0.0
    return precision, recall


def variant_selection(sent_dicts: list[dict], w: dict, variant: str, n: int, seed: int = 0) -> set:
    if variant == "lead":
        return set(range(min(n, len(sent_dicts))))
    rnd = random.Random(seed)
    return set(rnd.sample(range(len(sent_dicts)), min(n, len(sent_dicts))))


def evaluate_document(sent_dicts: list[dict], w: dict, reference: list[str], lang: str, n: int,
                      doc_chars: int, ostis_selected: set | None = None) -> dict:
    texts = [s["text"] for s in sent_dicts]
    relevant = match_reference(texts, reference)
    ref_text = " ".join(reference)
    res = {"n_reference": len(relevant)}
    for v in VARIANTS:
        if v == "ostis" and ostis_selected is None:
            continue
        runs = range(50) if v == "random" else range(1)
        ps, rs, fs, r1s, r2s = [], [], [], [], []
        for seed in runs:
            if v == "ostis":
                chosen = set(ostis_selected)
            elif v not in ("lead", "random"):
                copy = [dict(s) for s in sent_dicts]
                chosen = _select_variant(copy, w, v, n, doc_chars)
            else:
                chosen = variant_selection(sent_dicts, w, v, n, seed)
            p, r, f = prf(chosen, relevant)
            summary = " ".join(texts[i] for i in sorted(chosen))
            ps.append(p); rs.append(r); fs.append(f)
            r1s.append(rouge_n(summary, ref_text, lang, 1)); r2s.append(rouge_n(summary, ref_text, lang, 2))
        res[v] = {"precision": statistics.mean(ps), "recall": statistics.mean(rs), "f1": statistics.mean(fs),
                  "rouge1": statistics.mean(r1s), "rouge2": statistics.mean(r2s)}
    return res


def _select_variant(sent_dicts, w, variant, n, doc_chars):
    weigh_sentences({"chars": doc_chars, "sentences": sent_dicts}, w,
                    use_posd=variant in ("full", "score_posd"), use_posp=variant in ("full", "score_posp"))
    return set(select_sentences(sent_dicts, n))
