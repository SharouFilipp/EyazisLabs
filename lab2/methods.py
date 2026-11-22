import math
import random
from collections import Counter
from typing import Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier

from text_processor import normalize, sentences, tokenize

LANGUAGES = {'en': 'Английский', 'fr': 'Французский'}

MIN_PROB = 1e-6


class FrequentWordsMethod:

    name = 'frequent'
    title = 'Частотных слов'

    def __init__(self, top_n: int = 200):
        self.top_n = top_n
        self.profiles: Dict[str, Dict[str, float]] = {}

    def fit(self, texts: Dict[str, str]):
        self.profiles = {}
        for lang, text in texts.items():
            words = tokenize(normalize(text))
            counts = Counter(words)
            total = len(words)
            self.profiles[lang] = {w: c / total for w, c in counts.most_common(self.top_n)}

    def scores(self, words: List[str]) -> Dict[str, float]:
        if not words:
            return {lang: -math.log(MIN_PROB) for lang in self.profiles}
        result = {}
        for lang, prof in self.profiles.items():
            s = sum(math.log(prof.get(w, MIN_PROB)) for w in words)
            result[lang] = -s / len(words)
        return result

    def to_dict(self):
        return {'top_n': self.top_n, 'profiles': self.profiles}

    def load_dict(self, d):
        self.top_n = d['top_n']
        self.profiles = d['profiles']


class ShortWordsMethod:

    name = 'short'
    title = 'Коротких слов'

    def __init__(self, max_len: int = 5, min_count: int = 3):
        self.max_len = max_len
        self.min_count = min_count
        self.profiles: Dict[str, Dict[str, float]] = {}

    def _short(self, words: List[str]) -> List[str]:
        return [w for w in words if len(w.rstrip("'")) <= self.max_len]

    def fit(self, texts: Dict[str, str]):
        self.profiles = {}
        for lang, text in texts.items():
            counts = Counter(self._short(tokenize(normalize(text))))
            kept = {w: c for w, c in counts.items() if c > self.min_count}
            total = sum(kept.values())
            self.profiles[lang] = dict(sorted(((w, c / total) for w, c in kept.items()),
                                              key=lambda x: -x[1]))

    def sentence_scores(self, sentence: str):
        words = self._short(tokenize(sentence))
        return {lang: sum(math.log(prof.get(w, MIN_PROB)) for w in words)
                for lang, prof in self.profiles.items()}, len(words)

    def scores(self, text: str) -> Dict[str, float]:
        total = {lang: 0.0 for lang in self.profiles}
        n = 0
        for sent in sentences(text):
            s, k = self.sentence_scores(sent)
            n += k
            for lang in total:
                total[lang] += s[lang]
        if n == 0:
            return {lang: -math.log(MIN_PROB) for lang in self.profiles}
        return {lang: -v / n for lang, v in total.items()}

    def sentence_votes(self, text: str) -> Dict[str, int]:
        votes = Counter()
        for sent in sentences(text):
            s, k = self.sentence_scores(sent)
            if k:
                votes[max(s, key=s.get)] += 1
        return {lang: votes.get(lang, 0) for lang in self.profiles}

    def to_dict(self):
        return {'max_len': self.max_len, 'min_count': self.min_count, 'profiles': self.profiles}

    def load_dict(self, d):
        self.max_len = d['max_len']
        self.min_count = d['min_count']
        self.profiles = d['profiles']


class NeuralMethod:

    name = 'neural'
    title = 'Нейросетевой'

    def __init__(self, hidden: int = 64, seed: int = 42):
        self.hidden = hidden
        self.seed = seed
        self.vectorizer = None
        self.model = None
        self.classes: List[str] = []
        self.info = {}

    @staticmethod
    def _fragments(text: str, rng: random.Random, count: int) -> List[str]:
        words = tokenize(normalize(text))
        frags = []
        for _ in range(count):
            length = rng.randint(3, 60)
            start = rng.randint(0, max(0, len(words) - length))
            frags.append(' '.join(words[start:start + length]))
        return frags

    def fit(self, texts: Dict[str, str], samples_per_lang: int = 1500):
        rng = random.Random(self.seed)
        self.classes = sorted(texts)
        x, y = [], []
        for idx, lang in enumerate(self.classes):
            frags = self._fragments(texts[lang], rng, samples_per_lang)
            x += frags
            y += [idx] * len(frags)

        self.vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(1, 3),
                                          max_features=4000, sublinear_tf=True)
        features = self.vectorizer.fit_transform(x)
        self.model = MLPClassifier(hidden_layer_sizes=(self.hidden,), activation='relu',
                                   max_iter=200, early_stopping=True, validation_fraction=0.15,
                                   random_state=self.seed)
        self.model.fit(features, y)
        self.info = {
            'samples': len(x),
            'features': len(self.vectorizer.vocabulary_),
            'hidden': self.hidden,
            'epochs': int(self.model.n_iter_),
            'val_accuracy': round(float(self.model.best_validation_score_), 4),
            'loss': round(float(self.model.loss_), 5),
        }

    def scores(self, text: str) -> Dict[str, float]:
        doc = ' '.join(tokenize(normalize(text)))
        proba = self.model.predict_proba(self.vectorizer.transform([doc]))[0]
        return {self.classes[int(c)]: float(1.0 - p) for c, p in zip(self.model.classes_, proba)}

    def top_ngrams(self, k: int = 15) -> Dict[str, List[str]]:
        w = self.model.coefs_[0] @ self.model.coefs_[1]
        w = w[:, 0] if w.ndim == 2 else w
        names = self.vectorizer.get_feature_names_out()
        order = np.argsort(w)

        def unique(indices):
            seen = []
            for i in indices:
                g = names[i].strip() or '␣'
                if g not in seen:
                    seen.append(g)
                if len(seen) == k:
                    break
            return seen

        neg, pos = self.classes[0], self.classes[1]
        return {pos: unique(order[::-1]), neg: unique(order)}
