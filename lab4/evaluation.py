from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"\w+(?:[-']\w+)*|[^\w\s]", re.UNICODE)


def tokens(s: str) -> list[str]:
    s = s.lower().replace("’", "'").replace(" ", " ")
    s = re.sub(r"\b(l|d|j|n|s|c|m|t|qu|jusqu|lorsqu|puisqu)'", r"\1' ", s)
    return TOKEN_RE.findall(s)


def ngrams(toks, n):
    return Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))


def bleu(hyps: list[str], refs: list[str], max_n: int = 4) -> dict:
    match, total = [0] * max_n, [0] * max_n
    hyp_len = ref_len = 0
    for h, r in zip(hyps, refs):
        ht, rt = tokens(h), tokens(r)
        hyp_len += len(ht)
        ref_len += len(rt)
        for n in range(1, max_n + 1):
            hc, rc = ngrams(ht, n), ngrams(rt, n)
            match[n - 1] += sum(min(c, rc[g]) for g, c in hc.items())
            total[n - 1] += max(len(ht) - n + 1, 0)
    precisions = []
    for n in range(max_n):
        if n == 0:
            precisions.append(match[0] / total[0] if total[0] else 0.0)
        else:
            precisions.append((match[n] + 1) / (total[n] + 1))
    if min(precisions) <= 0:
        return {"bleu": 0.0, "precisions": precisions, "bp": 0.0, "ratio": 0.0}
    bp = 1.0 if hyp_len > ref_len else math.exp(1 - ref_len / max(hyp_len, 1))
    score = bp * math.exp(sum(math.log(p) for p in precisions) / max_n)
    return {"bleu": score, "precisions": precisions, "bp": bp, "ratio": hyp_len / max(ref_len, 1)}


def chrf(hyps: list[str], refs: list[str], n: int = 6, beta: float = 2.0) -> float:
    precs, recs = [], []
    for k in range(1, n + 1):
        m = th = tr = 0
        for h, r in zip(hyps, refs):
            hs = re.sub(r"\s+", " ", h.lower().replace(" ", " "))
            rs = re.sub(r"\s+", " ", r.lower().replace(" ", " "))
            hc, rc = Counter(hs[i:i + k] for i in range(len(hs) - k + 1)), Counter(rs[i:i + k] for i in range(len(rs) - k + 1))
            m += sum(min(c, rc[g]) for g, c in hc.items())
            th += sum(hc.values())
            tr += sum(rc.values())
        precs.append(m / th if th else 0.0)
        recs.append(m / tr if tr else 0.0)
    p, r = sum(precs) / n, sum(recs) / n
    if p + r == 0:
        return 0.0
    return (1 + beta ** 2) * p * r / (beta ** 2 * p + r)


def split_reference(text: str) -> list[str]:
    out = []
    for par in re.split(r"\n\s*\n", text.strip()):
        par = re.sub(r"\s*\n\s*", " ", par.strip())
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9«])", par)
        out += [p.strip() for p in parts if p.strip()]
    return out
