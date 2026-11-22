import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import spacy

from evaluation import bleu, chrf, split_reference
from grammar import SPACY_MODEL
from lexicon import Lexicon
from transfer import Translator

REPEAT = 5
REPLENISH = sorted((ROOT / "data" / "replenishment").glob("*.txt"))


def machine_info() -> dict:
    release = platform.release()
    if platform.system() == "Windows" and int(platform.version().split(".")[-1] or 0) >= 22000:
        release = "11"
    info = {"os": f"{platform.system()} {release} ({platform.version()})", "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(), "ram_gb": None}
    try:
        if platform.system() == "Windows":
            import ctypes
            import winreg

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM(); m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            info["ram_gb"] = round(m.ullTotalPhys / 2**30, 1)
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            info["cpu"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        elif platform.system() == "Linux":
            text = open("/proc/cpuinfo", encoding="utf-8").read()
            info["cpu"] = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.startswith("model name")),
                               info["cpu"])
            info["ram_gb"] = round(int(open("/proc/meminfo").readline().split()[1]) / 2**20, 1)
        elif platform.system() == "Darwin":
            info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                         text=True).stdout.strip()
            info["ram_gb"] = round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                                      text=True).stdout) / 2**30, 1)
    except Exception:
        pass
    try:
        from db import connect
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SHOW server_version")
            info["postgresql"] = list(cur.fetchone().values())[0]
    except Exception:
        info["postgresql"] = None
    return info


def evaluate(tr: Translator, part: str, mode: str) -> dict:
    docs, hyps, refs = [], [], []
    words = unknown = 0
    for f in sorted((ROOT / "corpus" / part / "en").glob("*.txt")):
        src = f.read_text(encoding="utf-8")
        ref = split_reference((ROOT / "corpus" / part / "fr" / f.name).read_text(encoding="utf-8"))
        r = tr.translate(src, mode)
        hyp = [s["fr"] for s in r["sentences"]]
        assert len(hyp) == len(ref), f"{f.name}: {len(hyp)} предложений перевода, {len(ref)} в эталоне"
        docs.append({"name": f.stem, "title": src.split("\n")[0], "domain": "cs" if f.stem.startswith("cs") else "lit",
                     "detected": r["domain"], "words": r["stats"]["words"], "unknown": r["stats"]["unknown"],
                     "bleu": round(bleu(hyp, ref)["bleu"] * 100, 1), "chrf": round(chrf(hyp, ref) * 100, 1)})
        hyps += hyp
        refs += ref
        words += r["stats"]["words"]
        unknown += r["stats"]["unknown"]
    b = bleu(hyps, refs)
    by_dom = {}
    for d in ("cs", "lit"):
        idx = [i for i, x in enumerate(docs) if x["domain"] == d]
        by_dom[d] = {"bleu": round(statistics.mean(docs[i]["bleu"] for i in idx), 1),
                     "chrf": round(statistics.mean(docs[i]["chrf"] for i in idx), 1)}
    return {"bleu": round(b["bleu"] * 100, 1), "precisions": [round(p * 100, 1) for p in b["precisions"]],
            "bp": round(b["bp"], 3), "chrf": round(chrf(hyps, refs) * 100, 1), "words": words, "unknown": unknown,
            "coverage": round(100 * (words - unknown) / words, 1), "sentences": len(hyps), "by_domain": by_dom,
            "domain_errors": sum(1 for d in docs if d["detected"] != d["domain"]), "docs": docs}


def timing(tr: Translator) -> dict:
    texts = [f.read_text(encoding="utf-8") for f in sorted((ROOT / "corpus" / "test" / "en").glob("*.txt"))]
    out = {}
    for k in (1, 2, 4):
        joined = "\n\n".join(texts[:2] * k)
        runs = [tr.translate(joined) for _ in range(REPEAT)]
        out[str(k)] = {"words": runs[0]["stats"]["words"],
                       **{st: round(statistics.median(r["time_ms"][st] for r in runs), 1)
                          for st in ("analysis", "transfer", "synthesis", "total")}}
    return out


def main():
    t0 = time.perf_counter()
    nlp = spacy.load(SPACY_MODEL)
    load_ms = (time.perf_counter() - t0) * 1000
    base = Translator(nlp, Lexicon.from_seed())
    res = {"machine": machine_info(), "spacy_model": SPACY_MODEL, "spacy": spacy.__version__,
           "load_ms": round(load_ms), "lexicon": base.lex.size(), "quality": {}}
    for part in ("dev", "test"):
        for mode in ("transfer", "direct"):
            res["quality"][f"{part}_{mode}"] = evaluate(base, part, mode)
            q = res["quality"][f"{part}_{mode}"]
            print(f"{part:4} {mode:8}  BLEU {q['bleu']:5.1f}  chrF {q['chrf']:5.1f}  покрытие {q['coverage']:5.1f}%")
    if REPLENISH:
        full = Translator(nlp, Lexicon.from_seed(*REPLENISH))
        res["replenishment"] = {"files": [f.name for f in REPLENISH], "lexicon": full.lex.size()}
        for mode in ("transfer", "direct"):
            q = evaluate(full, "test", mode)
            res["replenishment"][f"test_{mode}"] = q
            print(f"test {mode:8}  после пополнения: BLEU {q['bleu']:5.1f}  chrF {q['chrf']:5.1f}  покрытие {q['coverage']:5.1f}%")
    res["timing"] = timing(base)
    print("время, мс:", res["timing"])
    out = ROOT / "results" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
