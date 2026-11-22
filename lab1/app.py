import os
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db import init_db, get_db
from crawler import Crawler
from classifier import DocumentClassifier
from indexer import Indexer
from search import Search
from text_processor import TextProcessor
from evaluation import Evaluator


app = FastAPI(
    title='ИПС — Модуль индексирования (вариант 16)',
    description='Векторная модель поиска · Русский язык · Сфера: сеть Интернет',
    version='1.0',
)

init_db()

processor = TextProcessor()
indexer = Indexer(processor)
classifier = DocumentClassifier(processor, indexer.user_examples())
indexer.classifier = classifier
searcher = Search(processor)
crawler = Crawler()

os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')


class UrlList(BaseModel):
    urls: List[str]

class DeleteRequest(BaseModel):
    filename: str

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    category: Optional[str] = None

class CategoryRequest(BaseModel):
    category: Optional[str] = None

class EvaluateRequest(BaseModel):
    retrieved: List[int] = []
    relevant: List[int] = []


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')


@app.get('/api/documents')
def list_documents():
    docs = indexer.list_documents()
    return [{
        'id': d['id'],
        'filename': d['filename'],
        'title': d['title'],
        'date': d['uploaded_at'].strftime('%Y-%m-%d %H:%M'),
        'size': d['size'],
        'source_url': d.get('source_url') or '',
        'source_type': d.get('source_type') or 'file',
        'category': d.get('category') or '—',
        'category_manual': bool(d.get('category_manual')),
    } for d in docs]


@app.get('/api/documents/hashes')
def document_hashes():
    return indexer.get_hashes()


def _make_title(filename: str, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return os.path.splitext(filename)[0]


def _decode_and_normalize(raw: bytes) -> str:
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('cp1251', errors='replace')
    return text.replace('\r\n', '\n').replace('\r', '\n')


@app.post('/api/documents/upload')
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, 'Файлы не переданы')

    added, updated, errors = [], [], []
    for f in files:
        fn = os.path.basename((f.filename or '').strip())
        if not fn:
            continue
        if fn.startswith('~$') or fn.startswith('.') or fn.endswith('.tmp'):
            continue
        if not fn.lower().endswith(('.txt', '.md', '.text')):
            errors.append(f'{fn}: только .txt/.md')
            continue

        raw = await f.read()
        text = _decode_and_normalize(raw)

        action = indexer.upsert(
            fn, _make_title(fn, text), text,
            source_type='file', source_url=None, save_to_disk=True,
        )
        if action == 'added':
            added.append(fn)
        elif action == 'updated':
            updated.append(fn)

    if added or updated:
        indexer.build()
        print(f'[upload] added={len(added)} updated={len(updated)}')

    return {
        'ok': True, 'added': added, 'updated': updated,
        'errors': errors, 'total': len(indexer.list_documents()),
    }


@app.post('/api/documents/sync')
async def sync_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, 'Файлы не переданы')

    added, updated, skipped, errors = [], [], [], []
    for f in files:
        fn = os.path.basename((f.filename or '').strip())
        if not fn:
            continue
        if fn.startswith('~$') or fn.startswith('.') or fn.endswith('.tmp'):
            continue
        if not fn.lower().endswith(('.txt', '.md', '.text')):
            errors.append(f'{fn}: только .txt/.md')
            continue

        raw = await f.read()
        text = _decode_and_normalize(raw)

        action = indexer.upsert(
            fn, _make_title(fn, text), text,
            source_type='file', source_url=None,
            save_to_disk=False,
        )
        if action == 'added':
            added.append(fn)
        elif action == 'updated':
            updated.append(fn)
        elif action == 'skipped':
            skipped.append(fn)

    if added or updated:
        indexer.build()
        print(f'[sync] added={len(added)} updated={len(updated)} skipped={len(skipped)}')

    return {
        'ok': True, 'added': added, 'updated': updated,
        'skipped': skipped, 'errors': errors,
        'total': len(indexer.list_documents()),
    }


@app.post('/api/documents/load_urls')
def load_urls(payload: UrlList):
    urls = [u.strip() for u in payload.urls if u.strip()]
    if not urls:
        raise HTTPException(400, 'URL не переданы')

    added, updated, errors = [], [], []
    for url in urls:
        res = crawler.load(url)
        if not res:
            errors.append(url)
            continue
        fn, title, text, surl = res

        action = indexer.upsert(
            fn, title, text,
            source_type='url', source_url=surl, save_to_disk=False,
        )
        if action == 'added':
            added.append(surl)
        elif action == 'updated':
            updated.append(surl)

    if added or updated:
        indexer.build()
        print('[+] Индекс пересобран автоматически (URL)')

    return {
        'ok': True, 'added': added, 'updated': updated,
        'errors': errors, 'total': len(indexer.list_documents()),
    }


@app.post('/api/documents/delete')
def delete_document(payload: DeleteRequest):
    ok = indexer.delete(payload.filename)
    if ok:
        indexer.build()
        print('[+] Индекс пересобран после удаления')
    return {'ok': ok}


@app.post('/api/documents/clear')
def clear_documents():
    indexer.clear()
    return {'ok': True}


@app.get('/api/documents/download/{filename:path}')
def download_document(filename: str):
    safe_name = os.path.basename(filename)
    path = os.path.join(indexer.UPLOAD_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, 'Файл не найден')
    return FileResponse(path, filename=safe_name, media_type='text/plain')


@app.get('/api/document/{doc_id}/text')
def get_document_text(doc_id: int):
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, filename, title, text, size,
                   uploaded_at, source_url, source_type, category
            FROM documents WHERE id = %s
        """, (doc_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, 'Документ не найден')

    doc_id_, filename, title, text, size, uploaded_at, source_url, source_type, category = row
    return {
        'id': doc_id_,
        'filename': filename,
        'title': title,
        'text': text,
        'size': size,
        'date': uploaded_at.strftime('%Y-%m-%d %H:%M'),
        'source_url': source_url or '',
        'source_type': source_type or 'file',
        'category': category or '—',
    }


@app.post('/api/index/build')
def build_index():
    indexer.build()
    return {'ok': True, **indexer.stats()}


@app.get('/api/index/stats')
def index_stats():
    return indexer.stats()


@app.get('/api/index/categories')
def category_stats():
    return indexer.category_stats()


@app.get('/api/classifier/classes')
def classifier_classes():
    return classifier.classes


@app.get('/api/classifier/info')
def classifier_info():
    return classifier.info()


@app.post('/api/documents/{doc_id}/category')
def set_document_category(doc_id: int, payload: CategoryRequest):
    if payload.category is not None and payload.category not in classifier.classes:
        raise HTTPException(400, 'Неизвестная тема')
    if not indexer.set_category(doc_id, payload.category):
        raise HTTPException(404, 'Документ не найден')

    retrained = classifier.fit(indexer.user_examples())
    if retrained:
        indexer.classify_all()
    return {'ok': True, 'retrained': retrained, **classifier.info()}


@app.post('/api/classifier/predict')
def classifier_predict(payload: SearchRequest):
    return {
        'category': classifier.predict(payload.query),
        'proba': classifier.predict_proba(payload.query),
    }


@app.post('/api/search')
def search(payload: SearchRequest):
    q = payload.query.strip()
    if not q:
        raise HTTPException(400, 'Пустой запрос')
    results = searcher.search(q, top_k=payload.top_k, category=payload.category)
    return {'ok': True, 'results': [r.__dict__ for r in results]}


@app.post('/api/evaluate')
def evaluate(payload: EvaluateRequest):
    metrics = Evaluator.evaluate(payload.retrieved, set(payload.relevant))
    return {'ok': True, 'metrics': metrics}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='127.0.0.1', port=8000, reload=True)