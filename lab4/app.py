from __future__ import annotations

import glob
import io
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import spacy
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import french as F
from db import Json, connect, init_db, seed_dictionary
from evaluation import bleu, chrf, split_reference
from grammar import GENDER_RU, POS_RU, SPACY_MODEL
from lexicon import Lexicon
from suggest import suggest
from transfer import Translator

BASE = Path(__file__).resolve().parent
CORPUS = BASE / "corpus"
app = FastAPI(title="ЛР4 — машинный перевод EN→FR")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

STATE: dict = {}
LOCK = threading.Lock()
MODES = {"transfer": "система с трансфером", "direct": "прямой (пословно-оборотный) перевод"}
DOMAINS = {"cs": "научная статья (computer science)", "lit": "сочинение по литературе", None: "не определена"}


@app.on_event("startup")
def startup():
    t0 = time.perf_counter()
    STATE["nlp"] = spacy.load(SPACY_MODEL)
    STATE["db"] = init_db()
    reload_lexicon()
    STATE["load_ms"] = (time.perf_counter() - t0) * 1000


def reload_lexicon():
    with connect() as conn, conn.cursor() as cur:
        lex = Lexicon.from_db(cur)
    STATE["lex"] = lex
    STATE["tr"] = Translator(STATE["nlp"], lex)


def static_version() -> str:
    return str(int(max((BASE / "static" / f).stat().st_mtime for f in ("app.js", "style.css"))))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"samples": samples(), "v": static_version()})


def samples() -> list[dict]:
    out = []
    for part in ("test", "dev"):
        for f in sorted((CORPUS / part / "en").glob("*.txt")):
            text = f.read_text(encoding="utf-8")
            out.append({"id": f"{part}/{f.stem}", "title": text.strip().split("\n")[0], "part": part})
    return out


@app.get("/api/sample/{part}/{name}")
def sample(part: str, name: str):
    f = CORPUS / part / "en" / f"{name}.txt"
    if part not in ("test", "dev") or not f.exists():
        raise HTTPException(404, "Нет такого текста")
    return {"text": f.read_text(encoding="utf-8"), "title": f.read_text(encoding="utf-8").split("\n")[0]}


class TranslateIn(BaseModel):
    text: str
    title: str | None = None
    mode: str = "transfer"
    domain: str = "auto"
    save: bool = True


def run_translation(text: str, mode: str, domain: str) -> dict:
    if mode not in MODES:
        raise HTTPException(400, "Неизвестный режим перевода")
    dom = None if domain == "gen" else domain
    with LOCK:
        return STATE["tr"].translate(text, mode=mode, domain=dom)


@app.post("/api/translate")
def translate(req: TranslateIn):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Введите текст на английском языке")
    if len(text) > 100_000:
        raise HTTPException(400, "Текст слишком длинный (более 100 000 символов)")
    res = run_translation(text, req.mode, req.domain)
    title = (req.title or text.split("\n")[0])[:120]
    res["title"] = title
    res["mode_name"] = MODES[req.mode]
    res["domain_name"] = DOMAINS.get(res["domain"])
    if req.save:
        st = res["stats"]
        with connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO translations (title, source_text, result_text, mode, domain, n_words, n_translated,
                           n_unknown, coverage, time_ms, result) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (title, text, res["text"], req.mode, res["domain"], st["words"], st["translated"], st["unknown"],
                         st["coverage"], res["time_ms"]["total"], Json(res)))
            res["id"] = cur.fetchone()["id"]
            unk = {}
            for s in res["sentences"]:
                for t in s["tokens"]:
                    if t["status"] == "unknown":
                        key = (t["lemma"].lower(), t["pos"])
                        u = unk.setdefault(key, {"word": t["text"], "freq": 0, "example": s["en"][:200]})
                        u["freq"] += 1
            for (lemma, pos), u in unk.items():
                cur.execute("""INSERT INTO unknown_words (lemma, pos, word, freq, example) VALUES (%s,%s,%s,%s,%s)
                               ON CONFLICT (lemma, pos) DO UPDATE SET freq = unknown_words.freq + EXCLUDED.freq,
                               example = EXCLUDED.example, last_seen = NOW()""", (lemma, pos, u["word"], u["freq"], u["example"]))
    return res


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    name = file.filename or "file"
    ext = Path(name).suffix.lower()
    try:
        if ext == ".docx":
            import docx
            d = docx.Document(io.BytesIO(data))
            text = "\n\n".join(p.text.strip() for p in d.paragraphs if p.text.strip())
        elif ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n\n".join((pg.extract_text() or "") for pg in pdf.pages)
            text = re.sub(r"(?<![.!?:])\n(?!\n)", " ", text)
        elif ext in (".txt", ".md", ""):
            for enc in ("utf-8-sig", "utf-16", "cp1252"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            raise HTTPException(400, "Поддерживаются файлы TXT, DOCX и PDF")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")
    if not text.strip():
        raise HTTPException(400, "В файле нет текста")
    return {"title": Path(name).stem, "text": text.strip()}


@app.get("/api/translations")
def translations():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, created_at, title, mode, domain, n_words, n_translated, n_unknown, coverage, time_ms
                       FROM translations ORDER BY id DESC LIMIT 200""")
        return [dict(r, created_at=r["created_at"].strftime("%d.%m.%Y %H:%M")) for r in cur.fetchall()]


def load_translation(tid: int) -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM translations WHERE id = %s", (tid,))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Перевод не найден")
    res = r["result"]
    res.update(id=r["id"], title=r["title"], source_text=r["source_text"], created_at=r["created_at"].strftime("%d.%m.%Y %H:%M"),
               mode_name=MODES.get(r["mode"]), domain_name=DOMAINS.get(r["domain"]))
    return res


@app.get("/api/translations/{tid}")
def translation(tid: int):
    return load_translation(tid)


@app.delete("/api/translations/{tid}")
def delete_translation(tid: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM translations WHERE id = %s", (tid,))
    return {"ok": True}


@app.get("/api/translations/{tid}/report.txt")
def report_txt(tid: int, part: str = "all", enc: str = "utf-8"):
    r = load_translation(tid)
    txt = build_report(r, part)
    if enc == "utf-16":
        body, charset = txt.encode("utf-16"), "utf-16"
    else:
        body, charset = "﻿".encode("utf-8") + txt.encode("utf-8"), "utf-8"
    fname = f"translation_{tid}_{part}.txt"
    return Response(body, media_type=f"text/plain; charset={charset}",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def gram_info(e: dict) -> str:
    tr = e.get("translation") or {}
    parts = []
    if tr.get("gender"):
        parts.append(GENDER_RU.get(tr["gender"], tr["gender"]))
    if tr.get("plural") and tr["plural"] != tr.get("fr"):
        parts.append(f"мн. ч. {tr['plural']}")
    if tr.get("forms") and e["pos"] == "ADJ":
        parts.append("формы: " + ", ".join(dict.fromkeys(tr["forms"])))
    if tr.get("forms") and e["pos"] in ("VERB", "AUX"):
        parts.append("наст. вр.: " + ", ".join(tr["forms"]) + f"; прич. прош. вр. {tr.get('pp', '')}")
    return "; ".join(parts)


def build_report(r: dict, part: str = "all") -> str:
    st = r["stats"]
    L = []
    if part in ("all", "translation"):
        L += ["РЕЗУЛЬТАТ МАШИННОГО ПЕРЕВОДА (англо-французский)", "=" * 60,
              f"Документ: {r['title']}", f"Дата: {r.get('created_at', datetime.now().strftime('%d.%m.%Y %H:%M'))}",
              f"Метод: {r.get('mode_name')}", f"Предметная область: {r.get('domain_name')}",
              f"Слов во входном тексте: {st['words']}", f"Переведено слов: {st['translated']}",
              f"Не найдено в словаре: {st['unknown']}", f"Имена собственные и числа (без перевода): {st['proper']}",
              f"Покрытие: {st['coverage']}%", f"Время перевода: {r['time_ms']['total']:.1f} мс", "",
              "ИСХОДНЫЙ ТЕКСТ (английский)", "-" * 60, r.get("source_text", ""), "",
              "ПЕРЕВОД (французский)", "-" * 60, r["text"], ""]
    if part in ("all", "freq"):
        L += ["СПИСОК СЛОВ ПО ЧАСТОТЕ ВСТРЕЧАЕМОСТИ", "-" * 60,
              f"{'№':>4}  {'Слово':<18} {'Част.':>5}  {'Часть речи (теги)':<42} {'Перевод':<26} Грамматическая информация"]
        for i, e in enumerate(r["freq"], 1):
            tr = e.get("translation") or {}
            pos = f"{e['pos_ru']} ({', '.join(e['tags'])})"
            fr = tr.get("fr") or "— нет в словаре —"
            L.append(f"{i:>4}  {e['lemma']:<18} {e['frequency']:>5}  {pos:<42} {fr:<26} {gram_info(e)}")
            extra = []
            if e.get("forms"):
                extra.append("формы в тексте: " + ", ".join(e["forms"]))
            if e.get("roles"):
                extra.append("роли: " + ", ".join(e["roles"]))
            if e.get("morph"):
                extra.append("морфология: " + "; ".join(e["morph"]))
            L.append(" " * 6 + " | ".join(extra))
        L.append("")
    if part == "all":
        unk = sorted({w for s in r["sentences"] for w in s["unknown"]})
        L += ["НЕПЕРЕВЕДЁННЫЕ СЛОВА", "-" * 60, ", ".join(unk) if unk else "нет", ""]
    return "\r\n".join(L)


class Entry(BaseModel):
    en: str
    pos: str
    fr: str
    gender: str | None = None
    extra: str = ""
    domain: str | None = None
    source: str = "user"


POS_LIST = ["NOUN", "VERB", "ADJ", "ADV", "ADP", "PROPN", "PRON", "DET", "CCONJ", "SCONJ", "NUM", "PART"]


def clean_entry(e: Entry) -> tuple:
    en, fr = e.en.strip().lower(), e.fr.strip()
    if not en or not fr:
        raise HTTPException(400, "Заполните английское слово и перевод")
    if e.pos not in POS_LIST:
        raise HTTPException(400, "Неизвестная часть речи")
    g = e.gender if e.gender in ("m", "f") else None
    if e.pos in ("NOUN", "PROPN") and not g:
        raise HTTPException(400, "Для существительного укажите род (m/f)")
    dom = e.domain if e.domain in ("cs", "lit") else None
    src = e.source if e.source in ("user", "auto") else "user"
    return en, e.pos, fr, g, e.extra.strip(), dom, src


@app.get("/api/dict")
def dict_list(q: str = "", pos: str = "", source: str = "", limit: int = Query(100, le=2000), offset: int = 0):
    where, args = [], []
    if q:
        where.append("(en ILIKE %s OR fr ILIKE %s)")
        args += [f"%{q}%", f"%{q}%"]
    if pos:
        where.append("pos = %s")
        args.append(pos)
    if source:
        where.append("source = %s")
        args.append(source)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM dictionary {w}", args)
        total = cur.fetchone()["n"]
        cur.execute(f"""SELECT id, en, pos, fr, gender, extra, domain, source, updated_at FROM dictionary {w}
                        ORDER BY en, pos LIMIT %s OFFSET %s""", args + [limit, offset])
        rows = [dict(r, updated_at=r["updated_at"].strftime("%d.%m.%Y")) for r in cur.fetchall()]
    return {"total": total, "items": rows}


@app.get("/api/dict/stats")
def dict_stats():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT pos, COUNT(*) AS n FROM dictionary GROUP BY pos ORDER BY n DESC")
        by_pos = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT source, COUNT(*) AS n FROM dictionary GROUP BY source")
        by_src = {r["source"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT COALESCE(domain, 'общ') AS d, COUNT(*) AS n FROM dictionary GROUP BY domain")
        by_dom = {r["d"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) AS n FROM phrases")
        nph = cur.fetchone()["n"]
    return {"by_pos": by_pos, "by_source": by_src, "by_domain": by_dom, "phrases": nph,
            "total": sum(x["n"] for x in by_pos), "pos_ru": POS_RU}


@app.post("/api/dict")
def dict_add(e: Entry):
    vals = clean_entry(e)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO dictionary (en, pos, fr, gender, extra, domain, source) VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING RETURNING id""", vals)
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "Такая запись уже есть в словаре")
        cur.execute("DELETE FROM unknown_words WHERE lemma = %s", (vals[0],))
    reload_lexicon()
    return {"id": row["id"]}


@app.put("/api/dict/{eid}")
def dict_update(eid: int, e: Entry):
    en, pos, fr, g, extra, dom, _ = clean_entry(e)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE dictionary SET en=%s, pos=%s, fr=%s, gender=%s, extra=%s, domain=%s,
                       source = CASE WHEN source = 'seed' THEN 'user' ELSE source END, updated_at = NOW()
                       WHERE id = %s RETURNING id""", (en, pos, fr, g, extra, dom, eid))
        if not cur.fetchone():
            raise HTTPException(404, "Запись не найдена")
    reload_lexicon()
    return {"ok": True}


@app.delete("/api/dict/{eid}")
def dict_delete(eid: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dictionary WHERE id = %s", (eid,))
    reload_lexicon()
    return {"ok": True}


@app.get("/api/unknown")
def unknown_words():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT lemma, pos, word, freq, example FROM unknown_words ORDER BY freq DESC, lemma LIMIT 500")
        rows = [dict(r) for r in cur.fetchall()]
    lex = STATE["lex"]
    out = []
    for r in rows:
        pos = r["pos"] if r["pos"] in POS_LIST else "NOUN"
        if lex.get(r["lemma"], pos):
            continue
        r["pos"] = pos
        r["suggestion"] = suggest(lex, r["lemma"], pos, r["word"])
        out.append(r)
    return out


@app.delete("/api/unknown")
def unknown_clear():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE unknown_words")
    return {"ok": True}


class Batch(BaseModel):
    items: list[Entry]


@app.post("/api/dict/batch")
def dict_batch(b: Batch):
    added = 0
    with connect() as conn, conn.cursor() as cur:
        for e in b.items:
            vals = clean_entry(e)
            cur.execute("""INSERT INTO dictionary (en, pos, fr, gender, extra, domain, source) VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT DO NOTHING RETURNING id""", vals)
            if cur.fetchone():
                added += 1
            cur.execute("DELETE FROM unknown_words WHERE lemma = %s AND pos = %s", (vals[0], vals[1]))
    reload_lexicon()
    return {"added": added}


@app.get("/api/dict/export.tsv")
def dict_export():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT en, pos, fr, gender, extra, domain, source FROM dictionary ORDER BY en, pos")
        rows = cur.fetchall()
    lines = ["en\tpos\tfr\tgender\textra\tdomain\tsource"] + \
        ["\t".join(r[k] or "" for k in ("en", "pos", "fr", "gender", "extra", "domain", "source")) for r in rows]
    body = "﻿" + "\r\n".join(lines)
    return Response(body.encode("utf-8"), media_type="text/tab-separated-values; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="dictionary_en_fr.tsv"'})


@app.post("/api/dict/import")
async def dict_import(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    items, bad = [], 0
    for line in text.splitlines():
        if not line.strip() or line.startswith(("en\t", "#")):
            continue
        parts = (re.split(r"\t|\|", line) + [""] * 7)[:7]
        try:
            items.append(Entry(en=parts[0], pos=parts[1].strip().upper(), fr=parts[2], gender=parts[3].strip() or None,
                               extra=parts[4], domain=parts[5].strip() or None, source="user"))
        except Exception:
            bad += 1
    ok = []
    for e in items:
        try:
            clean_entry(e)
            ok.append(e)
        except HTTPException:
            bad += 1
    res = dict_batch(Batch(items=ok))
    return {"added": res["added"], "rows": len(items), "skipped": bad}


@app.post("/api/dict/reset")
def dict_reset():
    with connect() as conn, conn.cursor() as cur:
        seed_dictionary(cur, replace=True)
    reload_lexicon()
    return {"ok": True}


@app.get("/api/phrases")
def phrases(q: str = ""):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, en, fr, kind, extra, source FROM phrases WHERE en ILIKE %s OR fr ILIKE %s ORDER BY en",
                    (f"%{q}%", f"%{q}%"))
        return [dict(r) for r in cur.fetchall()]


class PhraseIn(BaseModel):
    en: str
    fr: str
    kind: str = "FIX"
    extra: str = ""


@app.post("/api/phrases")
def phrase_add(p: PhraseIn):
    if p.kind not in ("NOUN", "VERB", "ADJ", "FIX") or not p.en.strip() or not p.fr.strip():
        raise HTTPException(400, "Проверьте оборот: англ. текст, перевод и тип")
    if p.kind == "NOUN" and not re.search(r"(^|;)\s*[mf]\s*(;|$)", p.extra):
        raise HTTPException(400, "Для именного оборота укажите род в поле «доп.»: m или f")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO phrases (en, fr, kind, extra, source) VALUES (%s,%s,%s,%s,'user')
                       ON CONFLICT (en, kind) DO UPDATE SET fr = EXCLUDED.fr, extra = EXCLUDED.extra, updated_at = NOW()""",
                    (p.en.strip().lower(), p.fr.strip(), p.kind, p.extra.strip()))
    reload_lexicon()
    return {"ok": True}


@app.delete("/api/phrases/{pid}")
def phrase_delete(pid: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM phrases WHERE id = %s", (pid,))
    reload_lexicon()
    return {"ok": True}


@app.get("/api/conjugate")
def conjugate(verb: str):
    refl, inf, rest = F.split_verb(verb.strip())
    tenses = {t: [F.finite(inf, t, p, pl) for pl in (False, True) for p in (1, 2, 3)] for t in ("pres", "impf", "fut", "cond")}
    return {"inf": verb, "tenses": tenses, "pp": F.past_participle(inf), "ppr": F.present_participle(inf),
            "aux": "être" if F.uses_etre(inf, refl) else "avoir"}


@app.get("/api/evaluate")
def evaluate(part: str = "test"):
    if part not in ("test", "dev"):
        raise HTTPException(400, "part = test | dev")
    docs, totals = [], {}
    for f in sorted((CORPUS / part / "en").glob("*.txt")):
        src = f.read_text(encoding="utf-8")
        ref = split_reference((CORPUS / part / "fr" / f.name).read_text(encoding="utf-8"))
        row = {"name": f.stem, "title": src.split("\n")[0], "domain": "cs" if f.stem.startswith("cs") else "lit"}
        for mode in ("transfer", "direct"):
            res = run_translation(src, mode, "auto")
            hyp = [s["fr"] for s in res["sentences"]]
            b = bleu(hyp, ref)
            row[mode] = {"bleu": b["bleu"] * 100, "chrf": chrf(hyp, ref) * 100, "coverage": res["stats"]["coverage"],
                         "unknown": res["stats"]["unknown"], "words": res["stats"]["words"], "time": res["time_ms"]["total"]}
            t = totals.setdefault(mode, {"hyp": [], "ref": [], "words": 0, "unknown": 0, "time": 0.0})
            t["hyp"] += hyp
            t["ref"] += ref
            t["words"] += res["stats"]["words"]
            t["unknown"] += res["stats"]["unknown"]
            t["time"] += res["time_ms"]["total"]
        row["detected_domain"] = res["domain"]
        docs.append(row)
    summary = {}
    for mode, t in totals.items():
        summary[mode] = {"bleu": bleu(t["hyp"], t["ref"])["bleu"] * 100, "chrf": chrf(t["hyp"], t["ref"]) * 100,
                         "words": t["words"], "unknown": t["unknown"],
                         "coverage": 100 * (t["words"] - t["unknown"]) / max(t["words"], 1), "time": t["time"]}
    return {"part": part, "docs": docs, "summary": summary}


@app.get("/api/info")
def info():
    lex = STATE["lex"]
    return {"lexicon": lex.size(), "spacy": SPACY_MODEL, "load_ms": STATE.get("load_ms"), "db": STATE.get("db")}
