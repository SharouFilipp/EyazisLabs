"""Подключение к PostgreSQL и схема базы данных lab3."""
import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    filename     TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    lang         VARCHAR(2) NOT NULL CHECK (lang IN ('fr', 'it')),
    domain       VARCHAR(3) NOT NULL CHECK (domain IN ('cs', 'lit')),
    pages        INTEGER NOT NULL DEFAULT 1,
    chars        INTEGER NOT NULL,
    words        INTEGER NOT NULL,
    n_paragraphs INTEGER NOT NULL,
    n_sentences  INTEGER NOT NULL,
    paragraphs   JSONB NOT NULL,
    reference    JSONB,
    uploaded_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sentences (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx          INTEGER NOT NULL,
    paragraph    INTEGER NOT NULL,
    text         TEXT NOT NULL,
    bd           INTEGER NOT NULL,
    bp           INTEGER NOT NULL,
    posd         DOUBLE PRECISION,
    posp         DOUBLE PRECISION,
    score        DOUBLE PRECISION,
    weight       DOUBLE PRECISION,
    in_summary   BOOLEAN NOT NULL DEFAULT FALSE,
    sem_weight   DOUBLE PRECISION,
    concepts     JSONB,
    in_summary_ostis BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (document_id, idx)
);

CREATE TABLE IF NOT EXISTS terms (
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stem         TEXT NOT NULL,
    surface      TEXT NOT NULL,
    tf           INTEGER NOT NULL,
    df           INTEGER NOT NULL,
    weight       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (document_id, stem)
);

CREATE TABLE IF NOT EXISTS doc_concepts (
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    concept      TEXT NOT NULL,
    name         TEXT NOT NULL,
    ru           TEXT NOT NULL,
    tf           INTEGER NOT NULL,
    a0           DOUBLE PRECISION NOT NULL,
    activation   DOUBLE PRECISION NOT NULL,
    parent       TEXT,
    PRIMARY KEY (document_id, concept)
);

CREATE TABLE IF NOT EXISTS summaries (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    method       VARCHAR(10) NOT NULL CHECK (method IN ('extraction', 'ostis')),
    n_sentences  INTEGER NOT NULL,
    db_size      INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    keywords     JSONB NOT NULL,
    scs          TEXT NOT NULL,
    time_ms      DOUBLE PRECISION NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, method)
);

CREATE INDEX IF NOT EXISTS idx_sentences_document ON sentences(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_lang ON documents(lang);
"""


def dsn() -> dict:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "dbname": os.environ.get("PGDATABASE", "lab3"),
        "user": os.environ.get("PGUSER", "ips"),
        "password": os.environ.get("PGPASSWORD", "ips"),
    }


@contextmanager
def connect():
    conn = psycopg2.connect(**dsn(), cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS = """
ALTER TABLE sentences ADD COLUMN IF NOT EXISTS sem_weight DOUBLE PRECISION;
ALTER TABLE sentences ADD COLUMN IF NOT EXISTS concepts JSONB;
ALTER TABLE sentences ADD COLUMN IF NOT EXISTS in_summary_ostis BOOLEAN NOT NULL DEFAULT FALSE;
"""

SUMMARY_COLUMNS = {"id", "document_id", "method", "n_sentences", "db_size", "summary_text",
                   "keywords", "scs", "time_ms", "created_at"}


def _columns(cur, table: str) -> set:
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def init_db():
    """Создаёт схему и обновляет таблицы, оставшиеся от предыдущей версии (один метод).

    Таблица summaries старой версии не имеет столбца method — она пересоздаётся
    (рефераты строятся заново кнопкой «Реферировать»), остальные таблицы
    дополняются новыми столбцами без потери данных.
    """
    with connect() as conn, conn.cursor() as cur:
        old = _columns(cur, "summaries")
        if old and not SUMMARY_COLUMNS <= old:
            cur.execute("DROP TABLE summaries")
        cur.execute(SCHEMA)
        cur.execute(MIGRATIONS)


__all__ = ["connect", "init_db", "Json"]
