import random
import time
from collections import Counter
from typing import Dict, List

from methods import LANGUAGES
from text_processor import normalize

FRAGMENT_LENGTHS = [1, 2, 3, 5, 10, 20, 50]


def summary(rows: List[Dict], methods: List[str]) -> Dict:
    out = {}
    for m in methods:
        done = [r for r in rows if m in r['results']]
        labeled = [r for r in done if r['true_lang']]
        correct = sum(r['results'][m]['lang'] == r['true_lang'] for r in labeled)
        times = [r['results'][m]['time_ms'] for r in done]
        confusion = {t: {p: 0 for p in LANGUAGES} for t in LANGUAGES}
        for r in labeled:
            confusion[r['true_lang']][r['results'][m]['lang']] += 1
        out[m] = {
            'processed': len(done),
            'by_lang': dict(Counter(r['results'][m]['lang'] for r in done)),
            'labeled': len(labeled),
            'correct': correct,
            'accuracy': round(correct / len(labeled), 4) if labeled else None,
            'avg_ms': round(sum(times) / len(times), 3) if times else None,
            'total_ms': round(sum(times), 2),
            'confusion': confusion,
        }
    agree = [r for r in rows if all(m in r['results'] for m in methods)]
    return {
        'documents': len(rows),
        'methods': out,
        'agreement': sum(len({r['results'][m]['lang'] for m in methods}) == 1 for r in agree),
        'compared': len(agree),
    }


def fragment_benchmark(identifier, docs: List[Dict], methods: List[str],
                       lengths: List[int] = None, per_doc: int = 10, seed: int = 1) -> Dict:
    lengths = lengths or FRAGMENT_LENGTHS
    rng = random.Random(seed)
    labeled = [d for d in docs if d['true_lang']]
    table = {m: {} for m in methods}
    for k in lengths + ['full']:
        samples = []
        for d in labeled:
            words = normalize(d['text']).split()
            if k == 'full':
                samples.append((d['text'], d['true_lang']))
                continue
            for _ in range(per_doc):
                start = rng.randint(0, max(0, len(words) - k))
                samples.append((' '.join(words[start:start + k]), d['true_lang']))
        for m in methods:
            correct, total_ms = 0, 0.0
            t0 = time.perf_counter()
            for text, lang in samples:
                r = identifier.detect(text, [m])[m]
                correct += r['lang'] == lang
                total_ms += r['time_ms']
            table[m][str(k)] = {
                'samples': len(samples),
                'accuracy': round(correct / len(samples), 4) if samples else None,
                'avg_ms': round(total_ms / len(samples), 4) if samples else None,
                'wall_ms': round((time.perf_counter() - t0) * 1000, 1),
            }
    return {'lengths': [str(k) for k in lengths] + ['full'], 'documents': len(labeled), 'table': table}
