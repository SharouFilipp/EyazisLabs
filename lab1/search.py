import math
from collections import defaultdict
from dataclasses import dataclass

from db import get_db
from text_processor import TextProcessor


@dataclass
class SearchResult:
    document_id: int
    filename: str
    title: str
    snippet: str
    rank: float
    date: str
    matched_terms: list
    source_url: str
    source_type: str
    category: str


class Search:
    def __init__(self, processor: TextProcessor):
        self.processor = processor

    def search(self, query: str, top_k: int = 10, category: str = None):
        lemmas = list(set(self.processor.process(query)))
        if not lemmas:
            return []

        with get_db() as conn, conn.cursor() as cur:
            cur.execute('INSERT INTO queries_log (query) VALUES (%s)', (query,))

            cur.execute('SELECT id, lemma FROM terms WHERE lemma = ANY(%s)', (lemmas,))
            rows = cur.fetchall()
            if not rows:
                return []
            term_ids = [r[0] for r in rows]
            lemma_by_id = {r[0]: r[1] for r in rows}
            norm_q = math.sqrt(len(term_ids))

            cur.execute("""
                SELECT document_id, term_id, weight
                FROM doc_terms WHERE term_id = ANY(%s)
            """, (term_ids,))
            links = cur.fetchall()

            dots, matched = defaultdict(float), defaultdict(set)
            cur.execute('SELECT document_id, SUM(weight*weight) FROM doc_terms GROUP BY document_id')
            norms_sq = {r[0]: r[1] for r in cur.fetchall()}

            for doc_id, term_id, weight in links:
                dots[doc_id] += weight
                matched[doc_id].add(lemma_by_id[term_id])

            scored = []
            for doc_id, dot in dots.items():
                nd = math.sqrt(norms_sq.get(doc_id, 0))
                if nd == 0: continue
                scored.append((doc_id, dot / (nd * norm_q), sorted(matched[doc_id])))
            scored.sort(key=lambda x: x[1], reverse=True)

            if not scored:
                return []

            ids = [s[0] for s in scored]
            cur.execute("""
                SELECT id, filename, title, text, uploaded_at,
                       source_url, source_type, category
                FROM documents WHERE id = ANY(%s)
            """, (ids,))
            docs = {r[0]: r for r in cur.fetchall()}

            out = []
            for doc_id, score, matched_terms in scored:
                _, fn, title, text, dt, surl, stype, cat = docs[doc_id]
                if category and cat != category:
                    continue
                snippet = text[:300].strip() + ('…' if len(text) > 300 else '')
                out.append(SearchResult(
                    document_id=doc_id, filename=fn, title=title,
                    snippet=snippet, rank=round(score, 4),
                    date=dt.strftime('%Y-%m-%d %H:%M'),
                    matched_terms=matched_terms,
                    source_url=surl or '', source_type=stype or 'file',
                    category=cat or '—',
                ))
                if len(out) >= top_k:
                    break
            return out