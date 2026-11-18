"""Тестирование системы без интерфейса: время этапов, качество рефератов
при разной длине реферата, сводка по языкам и предметным областям.

Запуск: uv run python tools/benchmark.py   → results/benchmark.json
"""
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import evaluation  # noqa: E402
import ostis  # noqa: E402
from ostis_agent import SemanticAgent  # noqa: E402
from sc_memory import ScMemory  # noqa: E402
from doc_reader import read_document  # noqa: E402
from summarizer import (build_document, doc_stems, document_terms, keyword_tree,  # noqa: E402
                        select_sentences, summarize, term_weights, weigh_sentences)

REPEAT = 5
CORPUS = ROOT / "corpus" / "test"


def med(f, n=REPEAT):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter(); r = f(); ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts), r


def main():
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    docs, t_read = {}, {}
    for name in labels:
        t_read[name], docs[name] = med(lambda: read_document(CORPUS / name))
    df, size = {}, {}
    for lang in ("fr", "it"):
        c = Counter()
        names = [n for n in labels if labels[n]["lang"] == lang]
        for n in names:
            c.update(doc_stems(docs[n]["paragraphs"], lang))
        df[lang], size[lang] = c, len(names)

    agent = SemanticAgent()
    per_doc = []
    for name, lab in labels.items():
        lang, pars = lab["lang"], docs[name]["paragraphs"]
        stages = {}
        stages["split"], doc = med(lambda: build_document(pars, lang))
        stages["terms"], (tf, surface) = med(lambda: document_terms(doc, lang))
        stages["weights"], w = med(lambda: term_weights(tf, df[lang], size[lang]))
        stages["sentences"], _ = med(lambda: select_sentences(weigh_sentences(doc, w), 10))
        stages["keywords"], kws = med(lambda: keyword_tree(w, tf, surface, pars, lang, 10))
        t_total, res = med(lambda: summarize(pars, lang, df[lang], size[lang], 10, 10))
        chosen = [res["sentences"][i]["text"] for i in res["summary_idx"]]
        t_scs, scs = med(lambda: ostis.document_scs(1, lab["title"], lang, lab["domain"], "http://x", chosen,
                                                    res["keywords"]))
        item = {"name": name, "lang": lang, "domain": lab["domain"], "chars": lab["chars"],
                "paragraphs": len(pars), "sentences": len(res["sentences"]), "reference": len(lab["reference"]),
                "t_read": t_read[name], "t_total": t_total, "t_scs": t_scs, "stages": stages,
                "scs_lines": scs.count("\n") + 1, "by_n": {}}
        item["t_ostis"], sem10 = med(lambda: agent.summarize(pars, lang, 10, 10))
        t_sscs, sscs = med(lambda: ostis.semantic_scs(1, lang, [sem10["sentences"][i]["text"] for i in sem10["summary_idx"]],
                                                      sem10["keywords"]))
        item["t_ostis_scs"] = t_sscs
        for n in (5, 10, 15):
            sents = [dict(s) for s in res["sentences"]]
            sem = sem10 if n == 10 else agent.summarize(pars, lang, n, 10)
            item["by_n"][n] = evaluation.evaluate_document(sents, res["w"], lab["reference"], lang, n, res["doc"]["chars"],
                                                           set(sem["summary_idx"]))
        item["overlap"] = len(set(sem10["summary_idx"]) & set(res["summary_idx"]))
        item["kb_domain"] = sem10["domain"]
        item["n_concepts"] = sum(1 for c in sem10["concepts"] if c["tf"] > 0)
        item["sent_without_concepts"] = sum(1 for s in sem10["sentences"] if not s["concepts"])
        item["kw_ostis_precision"], item["kw_ostis_recall"] = evaluation.keyword_scores(sem10["keywords"], lab["keywords"], lang)
        item["ostis_last_par"] = sum(1 for i in sem10["summary_idx"] if sem10["sentences"][i]["paragraph"] == len(pars) - 1)
        item["ostis_hits"] = sorted(evaluation.match_reference([s["text"] for s in sem10["sentences"]], lab["reference"])
                                    & set(sem10["summary_idx"]))
        kp, kr = evaluation.keyword_scores(res["keywords"], lab["keywords"], lang)
        item["kw_precision"], item["kw_recall"] = kp, kr
        item["summary_hits"] = sorted(evaluation.match_reference([s["text"] for s in res["sentences"]],
                                                                  lab["reference"]) & set(res["summary_idx"]))
        per_doc.append(item)
        print(f"{name:15} read={t_read[name]:6.2f} мс  summ={t_total:6.2f} мс  "
              f"F1@10={item['by_n'][10]['full']['f1']:.3f}  Lead={item['by_n'][10]['lead']['f1']:.3f}  "
              f"KW P={kp:.2f} R={kr:.2f}  OSTIS F1={item['by_n'][10]['ostis']['f1']:.3f} "
              f"KW={item['kw_ostis_precision']:.2f}/{item['kw_ostis_recall']:.2f} пересеч={item['overlap']}")

    def mean(items, f):
        return statistics.mean(f(i) for i in items)
    groups = {}
    for key, flt in {"fr_cs": ("fr", "cs"), "fr_lit": ("fr", "lit"), "it_cs": ("it", "cs"), "it_lit": ("it", "lit"),
                     "fr": ("fr", None), "it": ("it", None), "cs": (None, "cs"), "lit": (None, "lit"),
                     "all": (None, None)}.items():
        items = [i for i in per_doc if (flt[0] in (None, i["lang"])) and (flt[1] in (None, i["domain"]))]
        g = {"count": len(items), "t_read": mean(items, lambda i: i["t_read"]),
             "t_total": mean(items, lambda i: i["t_total"]), "kw_precision": mean(items, lambda i: i["kw_precision"]),
             "kw_recall": mean(items, lambda i: i["kw_recall"]),
             "kw_ostis_precision": mean(items, lambda i: i["kw_ostis_precision"]),
             "kw_ostis_recall": mean(items, lambda i: i["kw_ostis_recall"]),
             "t_ostis": mean(items, lambda i: i["t_ostis"]), "overlap": mean(items, lambda i: i["overlap"]),
             "n_concepts": mean(items, lambda i: i["n_concepts"]),
             "stages": {s: mean(items, lambda i, s=s: i["stages"][s]) for s in items[0]["stages"]}, "by_n": {}}
        for n in (5, 10, 15):
            g["by_n"][n] = {v: {m: mean(items, lambda i, v=v, m=m: i["by_n"][n][v][m])
                                for m in ("precision", "recall", "f1", "rouge1", "rouge2")}
                            for v in evaluation.VARIANTS}
        groups[key] = g
    # вклад шагов семантического метода (F1 при N = 10 и точность ключевых понятий)
    def agent_run(**params):
        old = (agent.alpha, agent.beta, agent.use_domain, agent.use_spec)
        for k, v in params.items():
            setattr(agent, k, v)
        fs, kps = [], []
        for name, lab in labels.items():
            r = agent.summarize(docs[name]["paragraphs"], lab["lang"], 10, 10)
            rel = evaluation.match_reference([s["text"] for s in r["sentences"]], lab["reference"])
            fs.append(evaluation.prf(set(r["summary_idx"]), rel)[2])
            kps.append(evaluation.keyword_scores(r["keywords"], lab["keywords"], lab["lang"])[0])
        agent.alpha, agent.beta, agent.use_domain, agent.use_spec = old
        return {"f1": statistics.mean(fs), "kw_precision": statistics.mean(kps)}
    ablations = {
        "полный алгоритм": agent_run(),
        "без распространения активации (α = 0)": agent_run(alpha=0.0),
        "без штрафа за повтор понятий (β = 1)": agent_run(beta=1.0),
        "без определения предметной области": agent_run(use_domain=False),
        "без учёта специфичности понятий": agent_run(use_spec=False),
    }
    # проверка: сформированные фрагменты SCs разбираются sc-памятью
    mem = ScMemory()
    kb_files = mem.load_dir(ROOT / "kb")
    n_frag = 0
    for name, lab in list(labels.items())[:16]:
        r = agent.summarize(docs[name]["paragraphs"], lab["lang"], 10, 10)
        n_frag += mem.load_scs(ostis.semantic_scs(1, lab["lang"], [r["sentences"][i]["text"] for i in r["summary_idx"]],
                                                  r["keywords"]), name)
    kb = {"agent": agent.stats(), "roundtrip_sentences": n_frag, "kb_files": kb_files}
    out = ROOT / "results"; out.mkdir(exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps({"documents": per_doc, "groups": groups, "agent_ablations": ablations,
                                                    "kb": kb}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("вклад шагов:", {k: (round(v["f1"], 3), round(v["kw_precision"], 3)) for k, v in ablations.items()})
    a = groups["all"]
    print(f"\nвсе: F1@10 SE={a['by_n'][10]['full']['f1']:.3f} OSTIS={a['by_n'][10]['ostis']['f1']:.3f}  чтение={a['t_read']:.2f} мс  "
          f"SE={a['t_total']:.2f} мс  OSTIS={a['t_ostis']:.2f} мс  пересечение={a['overlap']:.2f}")


if __name__ == "__main__":
    main()
