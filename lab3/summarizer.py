import math
import re
import time
from collections import Counter, defaultdict

from stopwords import STOPWORDS
from text_processor import WORD_RE, is_term, split_sentences, stem, terms

LINK_WORDS = {
    "fr": {"de", "d", "du", "des", "à", "en"},
    "it": {"di", "del", "della", "dello", "dei", "degli", "delle", "a", "al", "alla", "da", "in"},
}


def build_document(paragraphs: list[str], lang: str) -> dict:
    sentences = []
    doc_text = "\n\n".join(paragraphs)
    doc_len = len(doc_text)
    offset = 0
    for p_idx, par in enumerate(paragraphs):
        for s_off, s_text in split_sentences(par, lang):
            sentences.append({
                "idx": len(sentences),
                "paragraph": p_idx,
                "text": s_text,
                "bd": offset + s_off,
                "bp": s_off,
                "plen": len(par),
                "terms": [s for s, _ in terms(s_text, lang)],
            })
        offset += len(par) + 2
    return {"text": doc_text, "chars": doc_len, "sentences": sentences}


def document_terms(doc: dict, lang: str) -> tuple[Counter, dict]:
    tf, forms = Counter(), defaultdict(Counter)
    for s, w in terms(doc["text"], lang):
        tf[s] += 1
        forms[s][w] += 1
    surface = {s: c.most_common(1)[0][0] for s, c in forms.items()}
    return tf, surface


def term_weights(tf: Counter, df: dict, db_size: int) -> dict:
    if not tf:
        return {}
    tf_max = max(tf.values())
    smooth = db_size < 2
    w = {}
    for t, f in tf.items():
        d = max(df.get(t, 1), 1)
        idf = math.log(1 + db_size / d) if smooth else math.log(db_size / d)
        w[t] = 0.5 * (1 + f / tf_max) * idf
    return w


def weigh_sentences(doc: dict, w: dict, use_posd=True, use_posp=True) -> list[dict]:
    D = max(doc["chars"], 1)
    for s in doc["sentences"]:
        tfs = Counter(s["terms"])
        s["score"] = sum(f * w.get(t, 0.0) for t, f in tfs.items())
        s["posd"] = 1 - s["bd"] / D
        s["posp"] = 1 - s["bp"] / max(s["plen"], 1)
        s["weight"] = s["score"] * (s["posd"] if use_posd else 1) * (s["posp"] if use_posp else 1)
    return doc["sentences"]


def select_sentences(sentences: list[dict], n: int, key="weight") -> list[int]:
    best = sorted(sentences, key=lambda s: (-s[key], s["idx"]))[:n]
    return sorted(s["idx"] for s in best)


def noun_phrases(paragraphs: list[str], lang: str, max_len: int = 3) -> Counter:
    stop = STOPWORDS[lang]
    links = LINK_WORDS[lang]
    phrases = Counter()
    for par in paragraphs:
        for _, sent in split_sentences(par, lang):
            toks = [t.lower() for t in WORD_RE.findall(sent)]
            n = len(toks)
            for i in range(n):
                if not is_term(toks[i], lang):
                    continue
                seq = [toks[i]]
                j = i + 1
                while j < n and len(seq) < max_len + 2:
                    t = toks[j]
                    if is_term(t, lang):
                        seq.append(t)
                        content = [x for x in seq if is_term(x, lang)]
                        if len(content) >= 2:
                            phrases[tuple(seq)] += 1
                        if len(content) >= max_len:
                            break
                    elif t in links and j + 1 < n and is_term(toks[j + 1], lang) and seq[-1] not in links:
                        seq.append(t)
                    else:
                        break
                    j += 1
    return phrases


def keyword_tree(w: dict, tf: Counter, surface: dict, paragraphs: list[str], lang: str,
                 n_keywords: int = 10, n_children: int = 3) -> list[dict]:
    top = sorted(w, key=lambda t: (-w[t], -tf[t], t))[:n_keywords]
    phrases = noun_phrases(paragraphs, lang)
    by_stems = defaultdict(lambda: {"count": 0, "forms": Counter()})
    for words_, cnt in phrases.items():
        key = tuple(stem(x, lang) if is_term(x, lang) else x for x in words_)
        by_stems[key]["count"] += cnt
        by_stems[key]["forms"][" ".join(words_)] += cnt
    tree = []
    for t in top:
        children = []
        for key, info in by_stems.items():
            if t in key and info["count"] >= 2:
                content = [k for k in key if k in w]
                pw = sum(w.get(k, 0) for k in content) * info["count"]
                children.append({"phrase": info["forms"].most_common(1)[0][0], "count": info["count"],
                                 "weight": round(pw, 4)})
        children.sort(key=lambda c: (-c["weight"], c["phrase"]))
        kept = []
        for c in children:
            if not any(c["phrase"] in k["phrase"] or k["phrase"] in c["phrase"] for k in kept):
                kept.append(c)
            if len(kept) >= n_children:
                break
        tree.append({"stem": t, "term": surface.get(t, t), "weight": round(w[t], 4), "tf": tf[t],
                     "children": kept})
    return tree


def summarize(paragraphs: list[str], lang: str, df: dict, db_size: int,
              n_sentences: int = 10, n_keywords: int = 10) -> dict:
    t0 = time.perf_counter()
    doc = build_document(paragraphs, lang)
    tf, surface = document_terms(doc, lang)
    w = term_weights(tf, df, db_size)
    sentences = weigh_sentences(doc, w)
    chosen = select_sentences(sentences, n_sentences)
    tree = keyword_tree(w, tf, surface, paragraphs, lang, n_keywords)
    elapsed = (time.perf_counter() - t0) * 1000
    for s in sentences:
        s["in_summary"] = s["idx"] in chosen
    return {
        "doc": doc, "tf": tf, "surface": surface, "w": w, "sentences": sentences,
        "summary_idx": chosen, "keywords": tree, "time_ms": elapsed,
        "smoothed_idf": db_size < 2,
    }


def doc_stems(paragraphs: list[str], lang: str) -> set:
    return {s for s, _ in terms("\n\n".join(paragraphs), lang)}


def clean_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
