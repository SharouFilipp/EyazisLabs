import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': os.environ.get('PGHOST', 'localhost'),
    'port': int(os.environ.get('PGPORT', 5432)),
    'dbname': os.environ.get('PGDATABASE', 'lab2'),
    'user': os.environ.get('PGUSER', 'ips'),
    'password': os.environ.get('PGPASSWORD', 'ips'),
}

DB_SCHEMA = os.environ.get('LAB2_SCHEMA', 'public')

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT UNIQUE NOT NULL,       -- имя PDF-файла в data/documents
    title       TEXT,                       -- заголовок из метаданных PDF или имя файла
    true_lang   VARCHAR(2),                 -- эталонный язык (en/fr) или NULL, если неизвестен
    pages       INTEGER,
    chars       INTEGER,                    -- длина извлечённого текста в символах
    words       INTEGER,                    -- число слов после предобработки
    text        TEXT NOT NULL,              -- текст, извлечённый из PDF
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS results (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    method      TEXT NOT NULL,              -- frequent / short / neural
    lang        VARCHAR(2) NOT NULL,        -- распознанный язык
    score_en    REAL,                       -- метрика расстояния до профиля английского
    score_fr    REAL,                       -- метрика расстояния до профиля французского
    confidence  REAL,
    time_ms     REAL,                       -- время распознавания, мс
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (document_id, method)
);
CREATE INDEX IF NOT EXISTS idx_results_document ON results(document_id);
"""


@contextmanager
def get_db():
    conn = psycopg2.connect(**DB_CONFIG, options=f'-c search_path={DB_SCHEMA}')
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    try:
        with get_db() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}')
            cur.execute(SCHEMA)
    except psycopg2.OperationalError as e:
        raise SystemExit(
            f'Не удалось подключиться к PostgreSQL ({DB_CONFIG["user"]}@{DB_CONFIG["host"]}:'
            f'{DB_CONFIG["port"]}/{DB_CONFIG["dbname"]}): {e}\n'
            'Создайте базу один раз от имени postgres:  psql -U postgres -f setup_db.sql'
        )
