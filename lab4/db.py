import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values

from lexicon import read_seed

SCHEMA = """
CREATE TABLE IF NOT EXISTS dictionary (
    id          SERIAL PRIMARY KEY,
    en          TEXT NOT NULL,                       -- английская лемма (для оборотов — через пробел)
    pos         VARCHAR(6) NOT NULL,                 -- часть речи: NOUN, VERB, ADJ, ADV, ADP, ...
    fr          TEXT NOT NULL,                       -- перевод (для глагола — инфинитив)
    gender      CHAR(1) CHECK (gender IN ('m', 'f')),
    extra       TEXT NOT NULL DEFAULT '',            -- формы и флаги: pl=…; f=…; pre; aux=être; obj=à
    domain      VARCHAR(3) CHECK (domain IN ('cs', 'lit')),
    source      VARCHAR(5) NOT NULL DEFAULT 'seed' CHECK (source IN ('seed', 'user', 'auto')),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS dictionary_uniq ON dictionary (en, pos, COALESCE(domain, ''), fr);
CREATE INDEX IF NOT EXISTS dictionary_en ON dictionary (en);

CREATE TABLE IF NOT EXISTS phrases (
    id          SERIAL PRIMARY KEY,
    en          TEXT NOT NULL,                       -- последовательность лемм
    fr          TEXT NOT NULL,
    kind        VARCHAR(5) NOT NULL CHECK (kind IN ('NOUN', 'VERB', 'ADJ', 'FIX', 'PROPN')),
    extra       TEXT NOT NULL DEFAULT '',
    source      VARCHAR(5) NOT NULL DEFAULT 'seed',
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (en, kind)
);

CREATE TABLE IF NOT EXISTS translations (
    id           SERIAL PRIMARY KEY,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    title        TEXT NOT NULL,
    source_text  TEXT NOT NULL,
    result_text  TEXT NOT NULL,
    mode         VARCHAR(8) NOT NULL CHECK (mode IN ('transfer', 'direct')),
    domain       VARCHAR(3),
    n_words      INTEGER NOT NULL,
    n_translated INTEGER NOT NULL,
    n_unknown    INTEGER NOT NULL,
    coverage     DOUBLE PRECISION NOT NULL,
    time_ms      DOUBLE PRECISION NOT NULL,
    result       JSONB NOT NULL                       -- предложения, частотный список, деревья
);

CREATE TABLE IF NOT EXISTS unknown_words (
    lemma       TEXT NOT NULL,
    pos         VARCHAR(6) NOT NULL,
    word        TEXT NOT NULL,
    freq        INTEGER NOT NULL DEFAULT 0,
    example     TEXT,
    last_seen   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (lemma, pos)
);
"""


def dsn() -> dict:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "dbname": os.environ.get("PGDATABASE", "lab4"),
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


def init_db() -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
        cur.execute("SELECT COUNT(*) AS n FROM dictionary")
        empty = cur.fetchone()["n"] == 0
        if empty:
            seed_dictionary(cur)
        cur.execute("SELECT COUNT(*) AS n FROM dictionary")
        n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM phrases")
        return {"dictionary": n, "phrases": cur.fetchone()["n"], "seeded": empty}


def seed_dictionary(cur, replace: bool = False) -> None:
    words, phrases = read_seed()
    if replace:
        cur.execute("DELETE FROM dictionary WHERE source = 'seed'")
        cur.execute("DELETE FROM phrases WHERE source = 'seed'")
    execute_values(cur, """INSERT INTO dictionary (en, pos, fr, gender, extra, domain) VALUES %s
                           ON CONFLICT DO NOTHING""",
                   [(w["en"], w["pos"], w["fr"], w["gender"], w["extra"], w["domain"]) for w in words])
    execute_values(cur, """INSERT INTO phrases (en, kind, fr, extra) VALUES %s ON CONFLICT (en, kind) DO NOTHING""",
                   [(p["en"], p["kind"], p["fr"], p["extra"]) for p in phrases])


__all__ = ["connect", "init_db", "seed_dictionary", "Json"]
