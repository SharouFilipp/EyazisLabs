import hashlib
import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from text_processor import TextProcessor
from training_data import TRAINING_DATA


MODEL_PATH = os.path.join('data', 'classifier.joblib')
UNKNOWN = 'Постороннее'

MIN_CONFIDENCE_RATIO = 1.5


def _join(lemmas):
    return ' '.join(lemmas)


class DocumentClassifier:
    def __init__(self, processor: TextProcessor, user_examples=()):
        self.processor = processor
        self.pipeline = None
        self.n_base = len(TRAINING_DATA)
        self.n_user = 0
        self.fit(user_examples)

    @staticmethod
    def _data_hash(user_examples):
        h = hashlib.sha256()
        for text, label in TRAINING_DATA:
            h.update(f'{label}\t{text}\n'.encode('utf-8'))
        for doc_id, content_hash, label, _ in sorted(user_examples):
            h.update(f'user\t{doc_id}\t{content_hash}\t{label}\n'.encode('utf-8'))
        return h.hexdigest()

    def fit(self, user_examples=()):
    
        user_examples = list(user_examples)
        data_hash = self._data_hash(user_examples)
        self.n_user = len(user_examples)
        if os.path.exists(MODEL_PATH):
            try:
                saved = joblib.load(MODEL_PATH)
                if isinstance(saved, dict) and saved.get('hash') == data_hash:
                    self.pipeline = saved['pipeline']
                    print('Классификатор загружен с диска')
                    return False
                print('Обучающая выборка изменилась — переобучение')
            except Exception as e:
                print(f'Не удалось загрузить модель: {e}')

        self._train(data_hash, user_examples)
        return True

    def _train(self, data_hash, user_examples):
        samples = list(TRAINING_DATA) + [(text, label)
                                         for _, _, label, text in user_examples]
        texts = [_join(self.processor.process(t)) for t, _ in samples]
        labels = [l for _, l in samples]

        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(sublinear_tf=True)),
            ('clf', MultinomialNB(alpha=0.1)),
        ])
        self.pipeline.fit(texts, labels)

        os.makedirs('data', exist_ok=True)
        joblib.dump({'hash': data_hash, 'pipeline': self.pipeline}, MODEL_PATH)
        print(f'Классификатор обучен на {len(texts)} примерах '
              f'(из них размечено пользователем: {len(user_examples)})')

    @property
    def classes(self):
        return list(self.pipeline.classes_) if self.pipeline else []

    def info(self):
        return {'classes': self.classes, 'base_examples': self.n_base,
                'user_examples': self.n_user,
                'total_examples': self.n_base + self.n_user}

    def proba_lemmas(self, lemmas) -> dict:
        if not lemmas or not self.pipeline:
            return {}
        probs = self.pipeline.predict_proba([_join(lemmas)])[0]
        return {str(c): round(float(p), 3)
                for c, p in zip(self.pipeline.classes_, probs)}

    def predict_lemmas(self, lemmas) -> str:
        probs = self.proba_lemmas(lemmas)
        if not probs:
            return UNKNOWN
        best = max(probs, key=probs.get)
        if probs[best] < MIN_CONFIDENCE_RATIO / len(probs):
            return UNKNOWN
        return best

    def predict(self, text: str) -> str:
        return self.predict_lemmas(self.processor.process(text or ''))

    def predict_proba(self, text: str) -> dict:
        return self.proba_lemmas(self.processor.process(text or ''))
