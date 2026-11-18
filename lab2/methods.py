import math
import random
from collections import Counter
from typing import Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier

from text_processor import normalize, sentences, tokenize

LANGUAGES = {'en': 'Английский', 'fr': 'Французский'}

# Вероятность, которая назначается слову, отсутствующему в ПОЯ.
# Одинакова для всех языков, поэтому «чужие» слова не смещают решение.
MIN_PROB = 1e-6


class FrequentWordsMethod:
    """Метод частотных слов.

    ПОЯ — top_n самых частотных слов обучающего текста с вероятностями
    p(w | L) = count(w) / N, где N — общее число слов обучающего текста языка.
    Метрика — средний отрицательный логарифм вероятности слов документа:
    d(D, L) = -1/|D| · Σ log p(w | L); отсутствующим словам назначается MIN_PROB.
    """

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
    """Метод коротких слов.

    ПОЯ — лексемы длиной не более max_len символов, встретившиеся в обучающем
    тексте более min_count раз. Вероятность лексемы — её частота, делённая на
    сумму частот всех лексем набора. Вероятность принадлежности предложения
    языку — произведение вероятностей его коротких лексем (в логарифмах — сумма);
    метрика документа — средний отрицательный логарифм по всем коротким лексемам
    всех предложений. Дополнительно считается, за какой язык «голосует»
    большинство предложений.
    """

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
        """Возвращает (логарифмы вероятностей предложения по языкам, число коротких лексем)."""
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
    """Нейросетевой метод.

    Признаки документа — TF-IDF веса символьных N-грамм (N = 1..3) внутри слов
    (слова берутся после предобработки, цифры и знаки препинания удалены).
    Классификатор — многослойный перцептрон (один скрытый слой, ReLU, softmax на выходе),
    обученный на фрагментах обучающих текстов случайной длины (от 3 до 60 слов),
    чтобы сеть уверенно работала и на коротких текстах.
    Метрика расстояния до языка: d(D, L) = 1 − P(L | D).
    """

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
        self.classes = sorted(texts)          # номер выходного класса -> код языка
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
        """N-граммы, сильнее всего «тянущие» выход сети к каждому языку
        (по произведению весов входного и выходного слоёв)."""
        w = self.model.coefs_[0] @ self.model.coefs_[1]   # (признаки × 1) для бинарного случая
        w = w[:, 0] if w.ndim == 2 else w
        names = self.vectorizer.get_feature_names_out()
        order = np.argsort(w)
        # для двух классов выход сети — вероятность второго класса

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
