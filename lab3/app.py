"""ЛР №3. Автоматическое реферирование документов (sentence extraction + OSTIS).
Вариант 6: французский и итальянский языки; научные статьи по computer science
и сочинения по литературе.

Реализованы два метода, которые работают параллельно:
  * sentence extraction — вес предложения Score·Posd·Posp (summarizer.py);
  * семантический метод OSTIS — агент реферирования по базе знаний предметных
    областей, загруженной в sc-память (sc_memory.py, ostis_agent.py).

Запуск: uv run uvicorn app:app --port 8003
"""
import json
import shutil
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import evaluation
import ostis
from ostis_agent import KB_DIR, SemanticAgent
from corpus_format import is_labeled, parse_labeled
from db import Json, connect, init_db
from doc_reader import SUPPORTED, ReadError, read_document
from summarizer import build_document, doc_stems, summarize
from text_processor import DOMAIN_NAMES, LANG_NAMES, detect_domain, detect_language, split_paragraphs, words

BASE = Path(__file__).resolve().parent
DOCS_DIR = BASE / "data" / "documents"
CORPUS_DIR = BASE / "corpus" / "test"

app = FastAPI(title="Автоматическое реферирование документов")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


AGENT: dict = {}
METHODS = {"extraction": "sentence extraction (Score·Posd·Posp)", "ostis": "семантический метод OSTIS"}


@app.on_event("startup")
def startup():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    AGENT["agent"] = SemanticAgent()     # загрузка базы знаний kb/*.scs в sc-память


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


# ---------------------------------------------------------------- документы

def _store_document(cur, path: Path, filename: str, lang: str = "auto", domain: str = "auto",
                    reference: dict | None = None) -> dict:
    info = read_document(path)
    text = "\n\n".join(info["paragraphs"])
    if lang not in LANG_NAMES:
        lang, _ = detect_language(text)
    if domain not in DOMAIN_NAMES:
        domain, _ = detect_domain(text, lang)
    doc = build_document(info["paragraphs"], lang)
    cur.execute(
        """INSERT INTO documents (filename, title, lang, domain, pages, chars, words, n_paragraphs,
                                  n_sentences, paragraphs, reference)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (filename) DO UPDATE SET title=EXCLUDED.title, lang=EXCLUDED.lang,
               domain=EXCLUDED.domain, pages=EXCLUDED.pages, chars=EXCLUDED.chars, words=EXCLUDED.words,
               n_paragraphs=EXCLUDED.n_paragraphs, n_sentences=EXCLUDED.n_sentences,
               paragraphs=EXCLUDED.paragraphs, reference=EXCLUDED.reference, uploaded_at=NOW()
           RETURNING id""",
        (filename, info["title"], lang, domain, info["pages"], len(text), len(words(text)),
         len(info["paragraphs"]), len(doc["sentences"]), Json(info["paragraphs"]),
         Json(reference) if reference else None))
    doc_id = cur.fetchone()["id"]
    # при замене документа старые результаты удаляются
    for table in ("sentences", "terms", "doc_concepts", "summaries"):
        cur.execute(f"DELETE FROM {table} WHERE document_id=%s", (doc_id,))
    return {"id": doc_id, "filename": filename, "title": info["title"], "lang": lang, "domain": domain}


@app.post("/api/documents")
async def upload(files: list[UploadFile] = File(...), lang: str = Form("auto"), domain: str = Form("auto")):
    added, errors = [], []
    with connect() as conn, conn.cursor() as cur:
        for f in files:
            name = Path(f.filename or "document").name
            if Path(name).suffix.lower() not in SUPPORTED:
                errors.append({"filename": name, "error": "поддерживаются только PDF, DOCX и TXT"})
                continue
            dest = DOCS_DIR / name
            with dest.open("wb") as out:
                shutil.copyfileobj(f.file, out)
            try:
                cur.execute("SAVEPOINT doc")
                d_lang, d_domain, ref = lang, domain, None
                if dest.suffix.lower() == ".txt":
                    text = dest.read_bytes().decode("utf-8-sig", errors="replace")
                    if is_labeled(text):
                        # исходный текст коллекции (corpus/src): метаданные и метки [*] -> эталон
                        lab = parse_labeled(text)
                        dest.write_text(lab["title"] + "\n\n" + "\n\n".join(lab["paragraphs"]), encoding="utf-8")
                        d_lang = lab["lang"] if lang not in LANG_NAMES else lang
                        d_domain = lab["domain"] if domain not in DOMAIN_NAMES else domain
                        if lab["reference"]:
                            ref = {"sentences": lab["reference"], "keywords": lab["keywords"]}
                added.append(_store_document(cur, dest, name, d_lang, d_domain, ref))
            except (ReadError, Exception) as e:  # noqa: BLE001 — сообщение показывается пользователю
                cur.execute("ROLLBACK TO SAVEPOINT doc")
                dest.unlink(missing_ok=True)
                errors.append({"filename": name, "error": str(e)})
    return {"added": added, "errors": errors}


@app.post("/api/collection")
def load_collection():
    """Загрузка тестовой коллекции с эталонной разметкой (corpus/test)."""
    labels = json.loads((CORPUS_DIR / "labels.json").read_text(encoding="utf-8"))
    added = []
    with connect() as conn, conn.cursor() as cur:
        for name, lab in labels.items():
            dest = DOCS_DIR / name
            shutil.copyfile(CORPUS_DIR / name, dest)
            ref = {"sentences": lab["reference"], "keywords": lab["keywords"]}
            added.append(_store_document(cur, dest, name, lab["lang"], lab["domain"], ref))
    return {"added": added, "errors": []}


@app.get("/api/documents")
def list_documents():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT d.id, d.filename, d.title, d.lang, d.domain, d.pages, d.chars, d.words,
                              d.n_paragraphs, d.n_sentences, d.reference IS NOT NULL AS has_reference,
                              d.uploaded_at, s.time_ms, s.created_at AS summarized_at, s.n_sentences AS summary_n,
                              o.time_ms AS time_ostis
                       FROM documents d
                       LEFT JOIN summaries s ON s.document_id = d.id AND s.method = 'extraction'
                       LEFT JOIN summaries o ON o.document_id = d.id AND o.method = 'ostis'
                       ORDER BY d.filename""")
        rows = cur.fetchall()
    for r in rows:
        r["uploaded_at"] = r["uploaded_at"].isoformat(timespec="seconds")
        r["summarized_at"] = r["summarized_at"].isoformat(timespec="seconds") if r["summarized_at"] else None
    return rows


class DocPatch(BaseModel):
    lang: str | None = None
    domain: str | None = None


@app.patch("/api/documents/{doc_id}")
def patch_document(doc_id: int, patch: DocPatch):
    """Ручное исправление языка или предметной области документа."""
    with connect() as conn, conn.cursor() as cur:
        if patch.lang in LANG_NAMES:
            cur.execute("UPDATE documents SET lang=%s WHERE id=%s", (patch.lang, doc_id))
        if patch.domain in DOMAIN_NAMES:
            cur.execute("UPDATE documents SET domain=%s WHERE id=%s", (patch.domain, doc_id))
        cur.execute("DELETE FROM summaries WHERE document_id=%s", (doc_id,))
    return {"ok": True}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s RETURNING filename", (doc_id,))
        row = cur.fetchone()
    if row:
        (DOCS_DIR / row["filename"]).unlink(missing_ok=True)
    return {"ok": bool(row)}


@app.delete("/api/documents")
def delete_all():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT filename FROM documents")
        for r in cur.fetchall():
            (DOCS_DIR / r["filename"]).unlink(missing_ok=True)
        # полная очистка коллекции: нумерация документов начинается заново
        cur.execute("TRUNCATE documents, sentences, terms, doc_concepts, summaries RESTART IDENTITY")
    return {"ok": True}


@app.get("/documents/{doc_id}/file")
def document_file(doc_id: int):
    """Активная ссылка на исходный документ: файл открывается в браузере."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT filename FROM documents WHERE id=%s", (doc_id,))
        row = cur.fetchone()
    if not row or not (DOCS_DIR / row["filename"]).exists():
        raise HTTPException(404, "Документ не найден")
    path = DOCS_DIR / row["filename"]
    media = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    return FileResponse(path, media_type=media.get(path.suffix.lower()),
                        headers={"Content-Disposition": "inline"})


# ---------------------------------------------------------------- реферирование

class SummarizeRequest(BaseModel):
    ids: list[int] | None = None
    n_sentences: int = 10
    n_keywords: int = 10


def _collection_df(cur, lang: str) -> tuple[Counter, int]:
    """df(t) — число документов коллекции (того же языка), содержащих термин t; |DB| — их число."""
    cur.execute("SELECT paragraphs FROM documents WHERE lang=%s", (lang,))
    rows = cur.fetchall()
    df = Counter()
    for r in rows:
        df.update(doc_stems(r["paragraphs"], lang))
    return df, len(rows)


def _summarize_row(cur, row, df, db_size, n_sentences, n_keywords, base_url):
    """Реферат документа обоими методами: sentence extraction и семантический метод OSTIS."""
    from psycopg2.extras import execute_values
    res = summarize(row["paragraphs"], row["lang"], df, db_size, n_sentences, n_keywords)
    sem = AGENT["agent"].summarize(row["paragraphs"], row["lang"], n_sentences, n_keywords)
    doc_id = row["id"]
    for table in ("sentences", "terms", "doc_concepts"):
        cur.execute(f"DELETE FROM {table} WHERE document_id=%s", (doc_id,))
    cid = {c: AGENT["agent"].concepts[c]["id"] for c in AGENT["agent"].concepts}
    execute_values(cur, """INSERT INTO sentences (document_id, idx, paragraph, text, bd, bp, posd, posp, score,
                                                  weight, in_summary, sem_weight, concepts, in_summary_ostis)
                           VALUES %s""",
                   [(doc_id, s["idx"], s["paragraph"], s["text"], s["bd"], s["bp"], s["posd"], s["posp"],
                     s["score"], s["weight"], s["in_summary"], ss["sem_weight"], Json([cid[c] for c in ss["concepts"]]),
                     ss["in_summary"]) for s, ss in zip(res["sentences"], sem["sentences"])])
    execute_values(cur, "INSERT INTO terms (document_id, stem, surface, tf, df, weight) VALUES %s",
                   [(doc_id, t, res["surface"][t], f, df.get(t, 1), res["w"][t]) for t, f in res["tf"].items()])
    if sem["concepts"]:
        execute_values(cur, """INSERT INTO doc_concepts (document_id, concept, name, ru, tf, a0, activation, parent)
                               VALUES %s""",
                       [(doc_id, c["concept"], c["name"], c["ru"], c["tf"], c["a0"], c["activation"], c["parent"])
                        for c in sem["concepts"]])
    url = f"{base_url}documents/{doc_id}/file"
    chosen = [res["sentences"][i]["text"] for i in res["summary_idx"]]
    chosen_sem = [sem["sentences"][i]["text"] for i in sem["summary_idx"]]
    scs = ostis.document_scs(doc_id, row["title"], row["lang"], row["domain"], url, chosen, res["keywords"])
    scs_sem = ostis.semantic_scs(doc_id, row["lang"], chosen_sem, sem["keywords"])
    for method, text, kws, frag, t in (("extraction", chosen, res["keywords"], scs, res["time_ms"]),
                                       ("ostis", chosen_sem, sem["keywords"], scs_sem, sem["time_ms"])):
        cur.execute("""INSERT INTO summaries (document_id, method, n_sentences, db_size, summary_text, keywords, scs,
                                              time_ms)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (document_id, method) DO UPDATE SET n_sentences=EXCLUDED.n_sentences,
                         db_size=EXCLUDED.db_size, summary_text=EXCLUDED.summary_text, keywords=EXCLUDED.keywords,
                         scs=EXCLUDED.scs, time_ms=EXCLUDED.time_ms, created_at=NOW()""",
                    (doc_id, method, n_sentences, db_size, "\n".join(text), Json(kws), frag, t))
    return {"id": doc_id, "time_ms": res["time_ms"], "time_ostis_ms": sem["time_ms"],
            "smoothed_idf": res["smoothed_idf"], "kb_domain": sem["domain"]}


@app.post("/api/summarize")
def summarize_documents(req: SummarizeRequest, request: Request):
    n_s = max(1, min(req.n_sentences, 50))
    n_k = max(1, min(req.n_keywords, 30))
    t0 = time.perf_counter()
    done = []
    with connect() as conn, conn.cursor() as cur:
        # одновременные запросы реферирования выполняются по очереди: иначе две транзакции
        # пишут предложения одного документа и вторая нарушает UNIQUE (document_id, idx)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (330621,))
        cur.execute("SELECT id, title, lang, domain, paragraphs FROM documents ORDER BY id")
        rows = [r for r in cur.fetchall() if req.ids is None or r["id"] in req.ids]
        by_lang = defaultdict(list)
        for r in rows:
            by_lang[r["lang"]].append(r)
        for lang, items in by_lang.items():
            df, db_size = _collection_df(cur, lang)
            for r in items:
                done.append(_summarize_row(cur, r, df, db_size, n_s, n_k, str(request.base_url)))
    return {"done": done, "total_ms": (time.perf_counter() - t0) * 1000}


def _load_summary(doc_id: int, method: str) -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM documents WHERE id=%s", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            raise HTTPException(404, "Документ не найден")
        cur.execute("SELECT * FROM summaries WHERE document_id=%s AND method=%s", (doc_id, method))
        summ = cur.fetchone()
        cur.execute("SELECT idx, paragraph, text, bd, bp, posd, posp, score, weight, in_summary, sem_weight, concepts, "
                    "in_summary_ostis FROM sentences WHERE document_id=%s ORDER BY idx", (doc_id,))
        sents = cur.fetchall()
        cur.execute("SELECT stem, surface, tf, df, weight FROM terms WHERE document_id=%s "
                    "ORDER BY weight DESC, tf DESC LIMIT 40", (doc_id,))
        top_terms = cur.fetchall()
        cur.execute("SELECT concept, name, ru, tf, a0, activation, parent FROM doc_concepts WHERE document_id=%s "
                    "ORDER BY activation DESC, concept LIMIT 40", (doc_id,))
        concepts = cur.fetchall()
    return {"doc": doc, "summary": summ, "sentences": sents, "terms": top_terms, "concepts": concepts}


@app.get("/api/documents/{doc_id}/summary")
def get_summary(doc_id: int, method: str = "extraction"):
    method = method if method in METHODS else "extraction"
    data = _load_summary(doc_id, method)
    doc, summ = data["doc"], data["summary"]
    if not summ:
        raise HTTPException(409, "Документ ещё не реферирован")
    sem = method == "ostis"
    key, flag = ("sem_weight", "in_summary_ostis") if sem else ("weight", "in_summary")
    ranks = sorted(data["sentences"], key=lambda s: (-(s[key] or 0), s["idx"]))
    rank_of = {s["idx"]: i + 1 for i, s in enumerate(ranks)}
    for s in data["sentences"]:
        s["rank"] = rank_of[s["idx"]]
        s["selected"] = s[flag]
    chosen = [s["text"] for s in data["sentences"] if s[flag]]
    graph = ostis.document_graph(doc_id, doc["title"], doc["lang"], doc["domain"], chosen, summ["keywords"], method)
    result = {
        "method": method, "method_name": METHODS[method],
        "doc": {k: doc[k] for k in ("id", "filename", "title", "lang", "domain", "pages", "chars", "words",
                                    "n_paragraphs", "n_sentences")},
        "lang_name": LANG_NAMES[doc["lang"]], "domain_name": DOMAIN_NAMES[doc["domain"]],
        "summary": chosen, "keywords": summ["keywords"], "sentences": data["sentences"],
        "terms": data["terms"], "concepts": data["concepts"], "scs": summ["scs"], "graph": graph,
        "time_ms": summ["time_ms"], "db_size": summ["db_size"],
        "created_at": summ["created_at"].isoformat(timespec="seconds"),
    }
    if doc["reference"]:
        sel = {s["idx"] for s in data["sentences"] if s[flag]}
        rel = evaluation.match_reference([s["text"] for s in data["sentences"]], doc["reference"]["sentences"])
        p, r, f = evaluation.prf(sel, rel)
        kp, kr = evaluation.keyword_scores(summ["keywords"], doc["reference"]["keywords"], doc["lang"])
        result["quality"] = {"precision": p, "recall": r, "f1": f, "kw_precision": kp, "kw_recall": kr,
                             "reference_idx": sorted(rel), "reference_keywords": doc["reference"]["keywords"]}
    return result


@app.get("/api/documents/{doc_id}/text")
def get_text(doc_id: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, filename, title, paragraphs FROM documents WHERE id=%s", (doc_id,))
        doc = cur.fetchone()
    if not doc:
        raise HTTPException(404, "Документ не найден")
    return doc


class TextRequest(BaseModel):
    text: str
    lang: str = "auto"
    n_sentences: int = 5
    n_keywords: int = 8
    method: str = "extraction"


@app.post("/api/text")
def summarize_text(req: TextRequest):
    """Реферирование произвольного текста выбранным методом; df — по коллекции + сам текст."""
    paragraphs = split_paragraphs(req.text)
    if not paragraphs:
        raise HTTPException(400, "Пустой текст")
    text = "\n\n".join(paragraphs)
    lang, lang_scores = detect_language(text) if req.lang not in LANG_NAMES else (req.lang, {})
    domain, _ = detect_domain(text, lang)
    n_s, n_k = max(1, req.n_sentences), max(1, req.n_keywords)
    with connect() as conn, conn.cursor() as cur:
        df, db_size = _collection_df(cur, lang)
    df = df.copy()
    df.update(doc_stems(paragraphs, lang))
    res = summarize(paragraphs, lang, df, db_size + 1, n_s, n_k)
    out = {"lang": lang, "lang_name": LANG_NAMES[lang], "lang_scores": lang_scores,
           "domain_name": DOMAIN_NAMES[domain], "db_size": db_size + 1, "n_sentences": len(res["sentences"])}
    if req.method == "ostis":
        sem = AGENT["agent"].summarize(paragraphs, lang, n_s, n_k)
        out.update(method="ostis", method_name=METHODS["ostis"],
                   kb_domain=DOMAIN_NAMES.get(sem["domain"], "не определена"),
                   summary=[sem["sentences"][i]["text"] for i in sem["summary_idx"]],
                   keywords=sem["keywords"], time_ms=sem["time_ms"], concepts=sem["concepts"][:15],
                   sentences=[{"idx": s["idx"], "text": s["text"], "weight": s["sem_weight"],
                               "concepts": len(s["concepts"]), "in_summary": s["in_summary"]} for s in sem["sentences"]])
    else:
        out.update(method="extraction", method_name=METHODS["extraction"],
                   summary=[res["sentences"][i]["text"] for i in res["summary_idx"]],
                   keywords=res["keywords"], time_ms=res["time_ms"],
                   sentences=[{k: s[k] for k in ("idx", "text", "posd", "posp", "score", "weight", "in_summary")}
                              for s in res["sentences"]])
    return out


# ---------------------------------------------------------------- оценка

@app.get("/api/evaluation")
def get_evaluation():
    """Оценка качества обоих методов по документам с эталонной разметкой."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT d.id, d.filename, d.title, d.lang, d.domain, d.chars, d.reference,
                              e.n_sentences, e.keywords, e.time_ms, o.keywords AS kw_ostis, o.time_ms AS time_ostis
                       FROM documents d JOIN summaries e ON e.document_id=d.id AND e.method='extraction'
                       JOIN summaries o ON o.document_id=d.id AND o.method='ostis' ORDER BY d.filename""")
        rows = cur.fetchall()
        per_doc = []
        for r in rows:
            cur.execute("SELECT idx, paragraph, text, bd, bp, score, weight, in_summary_ostis FROM sentences "
                        "WHERE document_id=%s ORDER BY idx", (r["id"],))
            sents = [dict(s) for s in cur.fetchall()]
            cur.execute("SELECT stem, weight FROM terms WHERE document_id=%s", (r["id"],))
            w = {t["stem"]: t["weight"] for t in cur.fetchall()}
            item = {"id": r["id"], "filename": r["filename"], "title": r["title"], "lang": r["lang"],
                    "domain": r["domain"], "time_ms": r["time_ms"], "time_ostis": r["time_ostis"],
                    "n_sentences": len(sents)}
            if r["reference"]:
                plen = defaultdict(int)
                for s in sents:
                    plen[s["paragraph"]] = max(plen[s["paragraph"]], s["bp"] + len(s["text"]))
                for s in sents:
                    s["plen"] = plen[s["paragraph"]]
                    s["terms"] = [t for t, _ in evaluation.terms(s["text"], r["lang"])]
                ostis_sel = {s["idx"] for s in sents if s["in_summary_ostis"]}
                item["metrics"] = evaluation.evaluate_document(sents, w, r["reference"]["sentences"], r["lang"],
                                                               r["n_sentences"], r["chars"], ostis_sel)
                ref_kw = r["reference"]["keywords"]
                item["kw_precision"], item["kw_recall"] = evaluation.keyword_scores(r["keywords"], ref_kw, r["lang"])
                item["kw_ostis_precision"], item["kw_ostis_recall"] = evaluation.keyword_scores(
                    r["kw_ostis"], ref_kw, r["lang"])
            per_doc.append(item)

    def agg(items):
        rated = [i for i in items if "metrics" in i]
        out = {"count": len(items), "rated": len(rated),
               "time_ms": statistics.mean(i["time_ms"] for i in items) if items else 0,
               "time_ostis": statistics.mean(i["time_ostis"] for i in items) if items else 0}
        if rated:
            for v in evaluation.VARIANTS:
                vals = [i["metrics"][v] for i in rated if v in i["metrics"]]
                if vals:
                    out[v] = {m: statistics.mean(x[m] for x in vals) for m in ("precision", "recall", "f1", "rouge1", "rouge2")}
            for k in ("kw_precision", "kw_recall", "kw_ostis_precision", "kw_ostis_recall"):
                out[k] = statistics.mean(i[k] for i in rated)
        return out

    groups = {}
    for lang in LANG_NAMES:
        for dom in DOMAIN_NAMES:
            items = [i for i in per_doc if i["lang"] == lang and i["domain"] == dom]
            if items:
                groups[f"{lang}_{dom}"] = {"lang": LANG_NAMES[lang], "domain": DOMAIN_NAMES[dom], **agg(items)}
    return {"documents": per_doc, "groups": groups, "total": agg(per_doc), "variants": evaluation.VARIANTS}


# ---------------------------------------------------------------- сохранение и OSTIS

def _report_items(ids: list[int] | None, base_url: str) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT d.id, d.filename, d.title, d.lang, d.domain, d.pages, d.n_sentences, d.words,
                              e.summary_text, e.keywords, e.time_ms, e.created_at,
                              o.summary_text AS summary_ostis, o.keywords AS kw_ostis, o.time_ms AS time_ostis
                       FROM documents d JOIN summaries e ON e.document_id=d.id AND e.method='extraction'
                       JOIN summaries o ON o.document_id=d.id AND o.method='ostis' ORDER BY d.filename""")
        rows = [r for r in cur.fetchall() if ids is None or r["id"] in ids]
    for r in rows:
        r["url"] = f"{base_url}documents/{r['id']}/file"
        r["sentences"] = r["summary_text"].split("\n")
        r["sentences_ostis"] = r["summary_ostis"].split("\n")
        r["lang_name"], r["domain_name"] = LANG_NAMES[r["lang"]], DOMAIN_NAMES[r["domain"]]
    return rows


@app.get("/api/report.html", response_class=HTMLResponse)
def report_html(request: Request, ids: str | None = None, download: int = 1):
    sel = [int(x) for x in ids.split(",")] if ids else None
    items = _report_items(sel, str(request.base_url))
    html = templates.get_template("report.html").render(items=items, now=datetime.now().strftime("%d.%m.%Y %H:%M"))
    name = f"summary_{items[0]['id']}.html" if sel and len(items) == 1 else "summaries_report.html"
    headers = {"Content-Disposition": f'attachment; filename="{name}"'} if download else {}
    return HTMLResponse(html, headers=headers)


@app.get("/api/report.txt", response_class=PlainTextResponse)
def report_txt(request: Request, ids: str | None = None):
    sel = [int(x) for x in ids.split(",")] if ids else None
    out = []
    for r in _report_items(sel, str(request.base_url)):
        out += [r["title"], f"Документ: {r['url']}",
                f"Язык: {r['lang_name']}; область: {r['domain_name']}; предложений в тексте: {r['n_sentences']}",
                "", "1. КЛАССИЧЕСКИЙ РЕФЕРАТ (sentence extraction)"]
        out += [f"{i}. {s}" for i, s in enumerate(r["sentences"], 1)]
        out += ["", "2. РЕФЕРАТ В ВИДЕ СПИСКА КЛЮЧЕВЫХ СЛОВ (sentence extraction)"]
        for kw in r["keywords"]:
            out.append(f"- {kw['term']} ({kw['weight']:.3f})")
            out += [f"    - {c['phrase']}" for c in kw["children"]]
        out += ["", "3. СЕМАНТИЧЕСКИЙ РЕФЕРАТ (OSTIS)"]
        out += [f"{i}. {s}" for i, s in enumerate(r["sentences_ostis"], 1)]
        out += ["", "4. КЛЮЧЕВЫЕ ПОНЯТИЯ БАЗЫ ЗНАНИЙ (OSTIS)"]
        for kw in r["kw_ostis"]:
            out.append(f"- {kw['term']} [{kw['ru']}] ({kw['weight']:.3f})")
            out += [f"    - {c['phrase']} [{c['ru']}]" for c in kw["children"]]
        out += ["", "=" * 70, ""]
    name = "summary.txt" if sel and len(sel) == 1 else "summaries_report.txt"
    return PlainTextResponse("\n".join(out), headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/kb.scs")
def knowledge_base(ids: str | None = None, method: str | None = None, with_domains: int = 0):
    """Фрагмент базы знаний OSTIS (SCs) с рефератами одного, нескольких или всех документов.
    with_domains=1 — вместе с онтологиями предметных областей."""
    sel = [int(x) for x in ids.split(",")] if ids else None
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT document_id, method, scs FROM summaries ORDER BY document_id, method")
        frags = [r["scs"] for r in cur.fetchall()
                 if (sel is None or r["document_id"] in sel) and (method is None or r["method"] == method)]
    text = ostis.knowledge_base(frags)
    if with_domains:
        text = "\n".join((KB_DIR / f).read_text(encoding="utf-8") for f in ("domain_cs.scs", "domain_lit.scs")) + "\n" + text
    name = f"document_{sel[0]}.scs" if sel and len(sel) == 1 else "summaries_kb.scs"
    return Response(text, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/kb/info")
def kb_info():
    """Сведения о базе знаний предметных областей в sc-памяти."""
    ag = AGENT["agent"]
    st = ag.stats()
    st["concepts_list"] = sorted(({"concept": v["id"], "ru": v["ru"], "domain": v["domain"], "depth": v["depth"],
                                   "parent": ag.concepts[v["parent"]]["id"] if v["parent"] else None,
                                   "fr": ag.memory.identifiers(c, "fr"), "it": ag.memory.identifiers(c, "it")}
                                  for c, v in ag.concepts.items()), key=lambda x: (x["domain"], x["concept"]))
    return st


@app.get("/api/kb/file/{name}")
def kb_file(name: str):
    path = KB_DIR / Path(name).name
    if path.suffix != ".scs" or not path.exists():
        raise HTTPException(404, "Файл базы знаний не найден")
    return FileResponse(path, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{path.name}"'})
