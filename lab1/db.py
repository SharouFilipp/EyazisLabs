import os
import psycopg2
from contextlib import contextmanager

DB_CONFIG = {
    'host': os.environ.get('PGHOST', 'localhost'),
    'port': int(os.environ.get('PGPORT', 5432)),
    'dbname': os.environ.get('PGDATABASE', 'lab1'),
    'user': os.environ.get('PGUSER', 'ips'),
    'password': os.environ.get('PGPASSWORD', 'ips'),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    filename     TEXT UNIQUE NOT NULL,
    title        TEXT,
    text         TEXT NOT NULL,
    size         INTEGER,
    content_hash TEXT,
    disk_path    TEXT,
    source_url   TEXT,
    source_type  TEXT DEFAULT 'file',
    category     TEXT,
    uploaded_at  TIMESTAMP DEFAULT NOW()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS disk_path    TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url   TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type  TEXT DEFAULT 'file';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category     TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS category_manual BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS terms (
    id SERIAL PRIMARY KEY, lemma TEXT UNIQUE NOT NULL, idf REAL
);
CREATE TABLE IF NOT EXISTS doc_terms (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    term_id     INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
    weight      REAL NOT NULL,
    PRIMARY KEY (document_id, term_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_terms_term ON doc_terms(term_id);
CREATE INDEX IF NOT EXISTS idx_doc_terms_doc  ON doc_terms(document_id);

CREATE TABLE IF NOT EXISTS queries_log (
    id SERIAL PRIMARY KEY, query TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW()
);
"""


@contextmanager
def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
    print('Схема БД инициализирована')