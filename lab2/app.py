import csv
import html
import io
import json
import os
import shutil
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


from pydantic import BaseModel

from db import get_db, init_db
from evaluation import fragment_benchmark, summary
from identifier import LanguageIdentifier
from methods import LANGUAGES
from pdf_reader import extract_text
from text_processor import normalize, tokenize

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE, 'data', 'documents')
TEST_DIR = os.path.join(BASE, 'corpus', 'test')

app = FastAPI(
    title='Автоматическое распознавание языка текста ',
    description='',
    version='1.0',
)

init_db()
os.makedirs(DOCS_DIR, exist_ok=True)
identifier = LanguageIdentifier()
METHOD_TITLES = {name: m.title for name, m in identifier.methods.items()}

app.mount('/static', StaticFiles(directory=os.path.join(BASE, 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(BASE, 'templates'))


class DetectRequest(BaseModel):
    ids: List[int] = []            
    methods: List[str] = []       

class TextRequest(BaseModel):
    text: str
    methods: List[str] = []

class LabelRequest(BaseModel):
    true_lang: Optional[str] = None

class BenchmarkRequest(BaseModel):
    methods: List[str] = []
    per_doc: int = 10



def _methods(requested: List[str]) -> List[str]:
    bad = [m for m in requested if m not in identifier.methods]
    if bad:
        raise HTTPException(400, f'Неизвестный метод: {", ".join(bad)}')
    return requested or list(identifier.methods)


def _load_rows(with_text: bool = False) -> List[dict]:
    with get_db() as cur:
        cur.execute('SELECT * FROM documents ORDER BY filename')
        docs = cur.fetchall()
        cur.execute('SELECT * FROM results')
        res = cur.fetchall()
    by_doc = {}
    for r in res:
        by_doc.setdefault(r['document_id'], {})[r['method']] = {
            'lang': r['lang'],
            'scores': {'en': r['score_en'], 'fr': r['score_fr']},
            'confidence': r['confidence'],
            'time_ms': r['time_ms'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
        }
    rows = []
    for d in docs:
        row = {k: d[k] for k in ('id', 'filename', 'title', 'true_lang', 'pages', 'chars', 'words')}
        row['uploaded_at'] = d['uploaded_at'].strftime('%Y-%m-%d %H:%M:%S')
        row['url'] = f'/documents/{d["id"]}/file'
        row['results'] = by_doc.get(d['id'], {})
        if with_text:
            row['text'] = d['text']
        rows.append(row)
    return rows


def _add_document(path: str, filename: str, true_lang: Optional[str]) -> dict:
    try:
        text, pages, meta_title = extract_text(path)
    except Exception as e:
        raise ValueError(f'не удалось прочитать PDF: {e}')
    if len(text) < 10:
        raise ValueError('в PDF нет текстового слоя (возможно, это скан)')
    words = len(tokenize(normalize(text)))
    title = meta_title or os.path.splitext(filename)[0]
    with get_db() as cur:
        cur.execute('DELETE FROM documents WHERE filename = %s', (filename,))
        cur.execute(
            'INSERT INTO documents (filename, title, true_lang, pages, chars, words, text) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id',
            (filename, title, true_lang, pages, len(text), words, text))
        return {'id': cur.fetchone()['id'], 'filename': filename, 'title': title}


def _save_results(doc_id: int, result: dict):
    with get_db() as cur:
        for m, r in result.items():
            cur.execute(
                'INSERT INTO results (document_id, method, lang, score_en, score_fr, confidence, time_ms) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s) '
                'ON CONFLICT (document_id, method) DO UPDATE SET lang = excluded.lang, '
                'score_en = excluded.score_en, score_fr = excluded.score_fr, '
                'confidence = excluded.confidence, time_ms = excluded.time_ms, '
                'created_at = NOW()',
                (doc_id, m, r['lang'], r['scores'].get('en'), r['scores'].get('fr'),
                 r['confidence'], r['time_ms']))

@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')


@app.get('/documents/{doc_id}/file')
def document_file(doc_id: int):
    with get_db() as cur:
        cur.execute('SELECT filename FROM documents WHERE id = %s', (doc_id,))
        d = cur.fetchone()
    if not d:
        raise HTTPException(404, 'Документ не найден')
    path = os.path.join(DOCS_DIR, d['filename'])
    if not os.path.exists(path):
        raise HTTPException(404, 'Файл документа отсутствует на диске')
    # inline — PDF открывается во вкладке браузера, а не скачивается
    return FileResponse(path, media_type='application/pdf', filename=d['filename'],
                        content_disposition_type='inline')


@app.get('/api/meta')
def meta():
    return {'languages': LANGUAGES, 'methods': METHOD_TITLES}


@app.get('/api/documents')
def list_documents():
    return _load_rows()


@app.get('/api/documents/{doc_id}/text')
def document_text(doc_id: int):
    with get_db() as cur:
        cur.execute('SELECT id, title, filename, text FROM documents WHERE id = %s', (doc_id,))
        d = cur.fetchone()
    if not d:
        raise HTTPException(404, 'Документ не найден')
    return dict(d)


@app.post('/api/documents/upload')
async def upload(files: List[UploadFile] = File(...), true_lang: str = Form('')):
    lang = true_lang if true_lang in LANGUAGES else None
    added, errors = [], []
    for f in files:
        name = os.path.basename(f.filename or '')
        if not name.lower().endswith('.pdf'):
            errors.append({'file': name, 'error': 'поддерживаются только PDF-файлы'})
            continue
        path = os.path.join(DOCS_DIR, name)
        with open(path, 'wb') as out:
            out.write(await f.read())
        try:
            added.append(_add_document(path, name, lang))
        except ValueError as e:
            os.remove(path)
            errors.append({'file': name, 'error': str(e)})
    return {'added': added, 'errors': errors}


@app.post('/api/documents/import-test')
def import_test_collection():
    with open(os.path.join(TEST_DIR, 'labels.json'), encoding='utf-8') as f:
        labels = json.load(f)
    added, errors = [], []
    for name, info in labels.items():
        dst = os.path.join(DOCS_DIR, name)
        shutil.copyfile(os.path.join(TEST_DIR, name), dst)
        try:
            added.append(_add_document(dst, name, info['lang']))
        except ValueError as e:
            errors.append({'file': name, 'error': str(e)})
    return {'added': added, 'errors': errors}


@app.put('/api/documents/{doc_id}/label')
def set_label(doc_id: int, req: LabelRequest):
    lang = req.true_lang if req.true_lang in LANGUAGES else None
    with get_db() as cur:
        cur.execute('UPDATE documents SET true_lang = %s WHERE id = %s', (lang, doc_id))
    return {'ok': True}


@app.delete('/api/documents/{doc_id}')
def delete_document(doc_id: int):
    with get_db() as cur:
        cur.execute('SELECT filename FROM documents WHERE id = %s', (doc_id,))
        d = cur.fetchone()
        if not d:
            raise HTTPException(404, 'Документ не найден')
        cur.execute('DELETE FROM documents WHERE id = %s', (doc_id,))
    path = os.path.join(DOCS_DIR, d['filename'])
    if os.path.exists(path):
        os.remove(path)
    return {'ok': True}


@app.delete('/api/documents')
def clear_documents():
    with get_db() as cur:
        cur.execute('DELETE FROM documents')
    for name in os.listdir(DOCS_DIR):
        os.remove(os.path.join(DOCS_DIR, name))
    return {'ok': True}


@app.post('/api/detect')
def detect_documents(req: DetectRequest):
    methods = _methods(req.methods)
    with get_db() as cur:
        if req.ids:
            cur.execute('SELECT id, text FROM documents WHERE id = ANY(%s)', (req.ids,))
        else:
            cur.execute('SELECT id, text FROM documents')
        docs = cur.fetchall()
    for d in docs:
        _save_results(d['id'], identifier.detect(d['text'], methods))
    rows = _load_rows()
    return {'processed': len(docs), 'documents': rows, 'summary': summary(rows, methods)}


@app.post('/api/detect/text')
def detect_text(req: TextRequest):
    if not req.text.strip():
        raise HTTPException(400, 'Введите текст')
    methods = _methods(req.methods)
    result = identifier.detect(req.text, methods)
    norm = normalize(req.text)
    return {
        'words': len(tokenize(norm)),
        'results': result,
        'short_votes': identifier.short.sentence_votes(norm) if 'short' in methods else None,
    }


@app.get('/api/stats')
def stats():
    rows = _load_rows()
    return {'summary': summary(rows, list(identifier.methods)), 'documents': rows}


@app.get('/api/profiles')
def profiles():
    return identifier.profiles_view()


@app.post('/api/train')
def retrain():
    return identifier.train()


@app.post('/api/benchmark')
def benchmark(req: BenchmarkRequest):
    methods = _methods(req.methods)
    docs = _load_rows(with_text=True)
    if not any(d['true_lang'] for d in docs):
        raise HTTPException(400, 'Нет документов с известным языком. Загрузите тестовую коллекцию.')
    return fragment_benchmark(identifier, docs, methods, per_doc=max(1, min(req.per_doc, 50)))



def _lang(code):
    return LANGUAGES.get(code, '—') if code else '—'


@app.get('/api/report')
def report(request: Request, fmt: str = 'html'):
    rows = _load_rows()
    methods = list(identifier.methods)
    s = summary(rows, methods)
    base = str(request.base_url).rstrip('/')

    if fmt == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=';')
        w.writerow(['id', 'Документ', 'Ссылка', 'Эталон']
                   + [f'{METHOD_TITLES[m]}: {c}' for m in methods for c in ('язык', 'd(en)', 'd(fr)', 'время, мс')])
        for r in rows:
            line = [r['id'], r['filename'], base + r['url'], _lang(r['true_lang'])]
            for m in methods:
                x = r['results'].get(m)
                line += [_lang(x['lang']), x['scores']['en'], x['scores']['fr'], x['time_ms']] if x else ['', '', '', '']
            w.writerow(line)
        w.writerow([])
        w.writerow(['Метод', 'Обработано', 'Английский', 'Французский', 'Точность', 'Среднее время, мс'])
        for m in methods:
            x = s['methods'][m]
            w.writerow([METHOD_TITLES[m], x['processed'], x['by_lang'].get('en', 0), x['by_lang'].get('fr', 0),
                        x['accuracy'] if x['accuracy'] is not None else '', x['avg_ms'] or ''])
        data = '﻿' + buf.getvalue()   
        return Response(data, media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="language_report.csv"'})

    head = ''.join(f'<th>{html.escape(METHOD_TITLES[m])}</th>' for m in methods)
    body = []
    for r in rows:
        cells = []
        for m in methods:
            x = r['results'].get(m)
            if not x:
                cells.append('<td>—</td>')
                continue
            bad = r['true_lang'] and x['lang'] != r['true_lang']
            cells.append(f'<td class="{"bad" if bad else ""}">{_lang(x["lang"])}'
                         f'<br><small>{x["time_ms"]:.2f} мс</small></td>')
        body.append(f'<tr><td>{r["id"]}</td><td><a href="{base}{r["url"]}">{html.escape(r["filename"])}</a></td>'
                    f'<td>{_lang(r["true_lang"])}</td>{"".join(cells)}</tr>')
    def accuracy_cell(x):
        if x['accuracy'] is None:
            return '—'
        return f"{x['accuracy'] * 100:.1f}% ({x['correct']}/{x['labeled']})"

    stat_rows = ''.join(
        f'<tr><td>{METHOD_TITLES[m]}</td><td>{x["processed"]}</td><td>{x["by_lang"].get("en", 0)}</td>'
        f'<td>{x["by_lang"].get("fr", 0)}</td><td>{accuracy_cell(x)}</td><td>{x["avg_ms"] or "—"}</td></tr>'
        for m, x in s['methods'].items())
    page = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>Отчёт о распознавании языка</title>
<style>
body{{font-family:Arial,sans-serif;margin:30px;color:#222}} h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #999;padding:5px 8px;text-align:left}}
th{{background:#eef1f7}} .bad{{background:#fde2e2}} small{{color:#666}}
</style></head><body>
<h1>Отчёт о распознавании языка текстовых документов</h1>
<p>Языки: английский, французский. Методы: частотных слов, коротких слов, нейросетевой.<br>
Документов в коллекции: {s['documents']}. Документов, по которым все методы дали одинаковый ответ: {s['agreement']} из {s['compared']}.</p>
<h2>Сводная статистика</h2>
<table><tr><th>Метод</th><th>Обработано</th><th>Английский</th><th>Французский</th><th>Точность</th><th>Среднее время, мс</th></tr>
{stat_rows}</table>
<h2>Результаты по документам</h2>
<table><tr><th>id</th><th>Документ</th><th>Эталон</th>{head}</tr>{''.join(body)}</table>
<script>if (location.search.includes('print=1')) window.print();</script>
</body></html>"""
    if fmt == 'view':
        return HTMLResponse(page)
    return Response(page, media_type='text/html; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="language_report.html"'})
