import hashlib
import math
import os
from collections import defaultdict

from db import get_db
from text_processor import TextProcessor


class Indexer:
    UPLOAD_DIR = os.path.join('data', 'uploads')

    def __init__(self, processor: TextProcessor, classifier=None):
        self.processor = processor
        self.classifier = classifier
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)

    def upsert(self, filename, title, text,
               category=None,
               source_type='file', source_url=None,
               save_to_disk=True) -> str:
        if not text or len(text.strip()) < 20:
            print(f'[!] Отклонён {filename}: слишком короткий текст ({len(text)})')
            return 'skipped'

        text = text.replace('\r\n', '\n').replace('\r', '\n')

        content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        disk_path = None

        if save_to_disk:
            disk_path = os.path.join(self.UPLOAD_DIR, filename)
            same = False
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, 'rb') as f:
                        existing = f.read()
                    new_bytes = text.encode('utf-8')
                    if existing == new_bytes:
                        same = True
                except Exception:
                    pass

            if not same:
                with open(disk_path, 'wb') as f:
                    f.write(text.encode('utf-8'))

        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documents
                    (filename, title, text, size, content_hash, disk_path,
                     source_url, source_type, category, uploaded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                ON CONFLICT (filename) DO UPDATE SET
                    title        = EXCLUDED.title,
                    text         = EXCLUDED.text,
                    size         = EXCLUDED.size,
                    content_hash = EXCLUDED.content_hash,
                    disk_path    = EXCLUDED.disk_path,
                    source_url   = EXCLUDED.source_url,
                    source_type  = EXCLUDED.source_type,
                    category     = CASE WHEN documents.category_manual
                                        THEN documents.category
                                        ELSE EXCLUDED.category END,
                    uploaded_at  = EXCLUDED.uploaded_at
                RETURNING (xmax = 0) AS inserted
            """, (filename, title, text, len(text), content_hash,
                  disk_path, source_url, source_type, category))
            row = cur.fetchone()
            return 'added' if row[0] else 'updated'

    def get_hashes(self):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('SELECT filename, content_hash FROM documents')
            return {fn: h for fn, h in cur.fetchall()}

    def delete(self, filename: str) -> bool:
        disk_path = os.path.join(self.UPLOAD_DIR, filename)
        if os.path.exists(disk_path):
            try:
                os.remove(disk_path)
            except OSError:
                pass
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('DELETE FROM documents WHERE filename = %s', (filename,))
            return cur.rowcount > 0

    def clear(self):
        if os.path.isdir(self.UPLOAD_DIR):
            for f in os.listdir(self.UPLOAD_DIR):
                try:
                    os.remove(os.path.join(self.UPLOAD_DIR, f))
                except OSError:
                    pass
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('TRUNCATE documents RESTART IDENTITY CASCADE')
            cur.execute('TRUNCATE terms RESTART IDENTITY CASCADE')

    def list_documents(self):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, filename, title, size, uploaded_at,
                       source_url, source_type, category, category_manual
                FROM documents ORDER BY id
            """)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def build(self):
        if self.classifier:
            self.classifier.fit(self.user_examples())

        with get_db() as conn, conn.cursor() as cur:
            cur.execute('DELETE FROM doc_terms')
            cur.execute('DELETE FROM terms')

            cur.execute('SELECT id, text, category_manual FROM documents')
            docs = cur.fetchall()
            N = len(docs)
            if N == 0:
                print('[!] Нет документов')
                return

            doc_tfs, df = {}, defaultdict(int)
            categories = []
            for doc_id, text, manual in docs:
                lemmas = self.processor.process(text)
                if self.classifier and not manual:
                    categories.append(
                        (self.classifier.predict_lemmas(lemmas), doc_id))
                tf = defaultdict(int)
                for l in lemmas:
                    tf[l] += 1
                doc_tfs[doc_id] = tf
                for l in tf:
                    df[l] += 1

            idf = {l: math.log((N + 1) / (d + 1)) + 1 for l, d in df.items()}

            cur.executemany(
                'INSERT INTO terms (lemma, idf) VALUES (%s, %s)',
                [(l, v) for l, v in idf.items()]
            )
            cur.execute('SELECT id, lemma FROM terms')
            term_ids = {l: i for i, l in cur.fetchall()}

            rows = []
            for doc_id, tf in doc_tfs.items():
                for l, freq in tf.items():
                    rows.append((doc_id, term_ids[l], freq * idf[l]))
            cur.executemany(
                'INSERT INTO doc_terms (document_id, term_id, weight) VALUES (%s,%s,%s)',
                rows
            )

            if categories:
                cur.executemany(
                    'UPDATE documents SET category = %s WHERE id = %s',
                    categories
                )
        print(f'[+] Индекс построен: {N} док., {len(idf)} терм.')

    def classify_all(self):
        if not self.classifier:
            return
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('SELECT id, text FROM documents WHERE NOT category_manual')
            categories = [
                (self.classifier.predict_lemmas(self.processor.process(text)), doc_id)
                for doc_id, text in cur.fetchall()
            ]
            cur.executemany(
                'UPDATE documents SET category = %s WHERE id = %s', categories)

    def user_examples(self):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, content_hash, category, text
                FROM documents WHERE category_manual
            """)
            return cur.fetchall()

    def set_category(self, doc_id: int, category):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE documents
                SET category = COALESCE(%s, category),
                    category_manual = %s
                WHERE id = %s
            """, (category, category is not None, doc_id))
            return cur.rowcount > 0

    def category_stats(self):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(category, 'Неизвестно'), COUNT(*)
                FROM documents GROUP BY category ORDER BY COUNT(*) DESC
            """)
            return [{'category': c, 'count': n} for c, n in cur.fetchall()]

    def stats(self):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM documents')
            n_d = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM terms')
            n_t = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM doc_terms')
            n_l = cur.fetchone()[0]
        return {'documents': n_d, 'terms': n_t, 'links': n_l}