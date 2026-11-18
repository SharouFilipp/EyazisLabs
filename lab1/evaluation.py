class Evaluator:
    @staticmethod
    def precision(retrieved, relevant):
        return 0.0 if not retrieved else len(set(retrieved) & relevant) / len(retrieved)

    @staticmethod
    def recall(retrieved, relevant):
        return 0.0 if not relevant else len(set(retrieved) & relevant) / len(relevant)

    @staticmethod
    def f1(p, r):
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    @staticmethod
    def average_precision(retrieved, relevant):
        if not relevant: return 0.0
        hits, total = 0, 0.0
        for i, d in enumerate(retrieved, start=1):
            if d in relevant:
                hits += 1; total += hits / i
        return total / len(relevant)

    @classmethod
    def evaluate(cls, retrieved, relevant):
        p = cls.precision(retrieved, relevant)
        r = cls.recall(retrieved, relevant)
        return {
            'precision': round(p, 4),
            'recall': round(r, 4),
            'f1': round(cls.f1(p, r), 4),
            'ap': round(cls.average_precision(retrieved, relevant), 4),
        }