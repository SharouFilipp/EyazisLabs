import hashlib
import json
import math
import os
import time
from typing import Dict, List

import joblib

from methods import LANGUAGES, FrequentWordsMethod, NeuralMethod, ShortWordsMethod
from text_processor import normalize, tokenize

BASE = os.path.dirname(os.path.abspath(__file__))
TRAIN_DIR = os.path.join(BASE, 'corpus', 'train')
PROFILE_DIR = os.path.join(BASE, 'data', 'profiles')


class LanguageIdentifier:
    def __init__(self):
        self.frequent = FrequentWordsMethod()
        self.short = ShortWordsMethod()
        self.neural = NeuralMethod()
        self.methods = {m.name: m for m in (self.frequent, self.short, self.neural)}
        self.train_info: Dict = {}
        self.load_or_train()

    @staticmethod
    def read_training_texts() -> Dict[str, str]:
        texts = {}
        for lang in LANGUAGES:
            with open(os.path.join(TRAIN_DIR, f'{lang}.txt'), encoding='utf-8') as f:
                texts[lang] = f.read()
        return texts

    @staticmethod
    def _hash(texts: Dict[str, str]) -> str:
        h = hashlib.sha256()
        for lang in sorted(texts):
            h.update(lang.encode() + texts[lang].encode('utf-8'))
        return h.hexdigest()

    def train(self) -> Dict:
        texts = self.read_training_texts()
        timings = {}
        for name, method in self.methods.items():
            t0 = time.perf_counter()
            method.fit(texts)
            timings[name] = round((time.perf_counter() - t0) * 1000, 1)

        self.train_info = {
            'hash': self._hash(texts),
            'trained_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'corpus': {lang: {'bytes': len(t.encode('utf-8')), 'chars': len(t),
                              'words': len(tokenize(normalize(t)))}
                       for lang, t in texts.items()},
            'train_ms': timings,
            'neural': self.neural.info,
        }
        os.makedirs(PROFILE_DIR, exist_ok=True)
        with open(os.path.join(PROFILE_DIR, 'frequent_words.json'), 'w', encoding='utf-8') as f:
            json.dump(self.frequent.to_dict(), f, ensure_ascii=False, indent=1)
        with open(os.path.join(PROFILE_DIR, 'short_words.json'), 'w', encoding='utf-8') as f:
            json.dump(self.short.to_dict(), f, ensure_ascii=False, indent=1)
        joblib.dump({'vectorizer': self.neural.vectorizer, 'model': self.neural.model,
                     'classes': self.neural.classes, 'info': self.neural.info}, os.path.join(PROFILE_DIR, 'neural.joblib'))
        with open(os.path.join(PROFILE_DIR, 'train_info.json'), 'w', encoding='utf-8') as f:
            json.dump(self.train_info, f, ensure_ascii=False, indent=1)
        return self.train_info

    def load_or_train(self):
        try:
            with open(os.path.join(PROFILE_DIR, 'train_info.json'), encoding='utf-8') as f:
                info = json.load(f)
            if info['hash'] != self._hash(self.read_training_texts()):
                raise ValueError('обучающий набор изменился')
            with open(os.path.join(PROFILE_DIR, 'frequent_words.json'), encoding='utf-8') as f:
                self.frequent.load_dict(json.load(f))
            with open(os.path.join(PROFILE_DIR, 'short_words.json'), encoding='utf-8') as f:
                self.short.load_dict(json.load(f))
            nn = joblib.load(os.path.join(PROFILE_DIR, 'neural.joblib'))
            self.neural.vectorizer, self.neural.model = nn['vectorizer'], nn['model']
            self.neural.classes, self.neural.info = nn['classes'], nn['info']
            self.train_info = info
        except (OSError, ValueError, KeyError):
            self.train()

    def detect(self, text: str, methods: List[str] = None) -> Dict[str, Dict]:
        methods = methods or list(self.methods)
        result = {}
        for name in methods:
            t0 = time.perf_counter()
            norm = normalize(text)                       
            if name == 'frequent':
                scores = self.frequent.scores(tokenize(norm))
            elif name == 'short':
                scores = self.short.scores(norm)
            else:
                scores = self.neural.scores(norm)          
            lang = min(scores, key=scores.get)           
            elapsed = (time.perf_counter() - t0) * 1000
            result[name] = {
                'lang': lang,
                'scores': {k: round(v, 5) for k, v in scores.items()},
                'confidence': round(self._confidence(name, scores), 4),
                'time_ms': round(elapsed, 3),
            }
        return result

    @staticmethod
    def _confidence(method: str, scores: Dict[str, float]) -> float:
        ordered = sorted(scores.values())
        if method == 'neural':
            return 1.0 - ordered[0]
        if len(ordered) < 2 or ordered[1] == 0:
            return 0.0
        return (ordered[1] - ordered[0]) / ordered[1]

    def profiles_view(self, limit: int = 40) -> Dict:
        return {
            'languages': LANGUAGES,
            'train_info': self.train_info,
            'frequent': {lang: list(p.items())[:limit] for lang, p in self.frequent.profiles.items()},
            'frequent_size': {lang: len(p) for lang, p in self.frequent.profiles.items()},
            'short': {lang: list(p.items())[:limit] for lang, p in self.short.profiles.items()},
            'short_size': {lang: len(p) for lang, p in self.short.profiles.items()},
            'neural_ngrams': self.neural.top_ngrams(20),
            'params': {
                'frequent_top_n': self.frequent.top_n,
                'short_max_len': self.short.max_len,
                'short_min_count': self.short.min_count,
            },
        }
