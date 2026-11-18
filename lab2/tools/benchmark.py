"""
Тестирование системы без веб-интерфейса: точность и быстродействие методов
на тестовой коллекции и на фрагментах разной длины. Результаты сохраняются
в results/benchmark.json, графики — в results/*.png.

Запуск:  uv run python tools/benchmark.py
"""

import json
import os
import platform
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from evaluation import fragment_benchmark, summary
from identifier import LanguageIdentifier
from pdf_reader import extract_text

OUT = os.path.join(ROOT, 'results')
TITLES = {'frequent': 'Частотных слов', 'short': 'Коротких слов', 'neural': 'Нейросетевой'}
COLORS = {'frequent': '#2f4a8c', 'short': '#d9822b', 'neural': '#3a9a6a'}


def main():
    os.makedirs(OUT, exist_ok=True)
    identifier = LanguageIdentifier()

    t0 = time.perf_counter()
    train_info = identifier.train()
    train_total = (time.perf_counter() - t0) * 1000

    test_dir = os.path.join(ROOT, 'corpus', 'test')
    with open(os.path.join(test_dir, 'labels.json'), encoding='utf-8') as f:
        labels = json.load(f)

    rows, extract_ms = [], []
    for name, info in labels.items():
        t = time.perf_counter()
        text, pages, _ = extract_text(os.path.join(test_dir, name))
        extract_ms.append((time.perf_counter() - t) * 1000)
        # 5 прогонов — для устойчивой оценки времени
        runs = [identifier.detect(text) for _ in range(5)]
        res = runs[-1]
        for m in res:
            res[m]['time_ms'] = round(statistics.median(r[m]['time_ms'] for r in runs), 3)
        rows.append({'filename': name, 'true_lang': info['lang'], 'chars': len(text),
                     'text': text, 'results': res})

    methods = list(identifier.methods)
    s = summary(rows, methods)
    bench = fragment_benchmark(identifier, rows, methods, per_doc=20)

    result = {
        'machine': f'{platform.processor()} · Python {platform.python_version()}',
        'train': train_info, 'train_total_ms': round(train_total, 1),
        'extract_avg_ms': round(statistics.mean(extract_ms), 2),
        'summary': s, 'fragments': bench,
        'documents': [{k: v for k, v in r.items() if k != 'text'} for r in rows],
    }
    with open(os.path.join(OUT, 'benchmark.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    # ---------- графики ----------
    labels_x = [('весь\nдокумент' if k == 'full' else k) for k in bench['lengths']]
    plt.figure(figsize=(8, 4.5))
    for m in methods:
        plt.plot(labels_x, [bench['table'][m][k]['accuracy'] * 100 for k in bench['lengths']],
                 marker='o', label=TITLES[m], color=COLORS[m])
    plt.xlabel('Длина фрагмента, слов')
    plt.ylabel('Точность, %')
    plt.title('Точность распознавания в зависимости от длины текста')
    plt.grid(alpha=.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'accuracy_by_length.png'), dpi=150)

    plt.figure(figsize=(8, 4.5))
    width = 0.27
    xs = range(len(bench['lengths']))
    for i, m in enumerate(methods):
        plt.bar([x + (i - 1) * width for x in xs],
                [bench['table'][m][k]['avg_ms'] for k in bench['lengths']],
                width, label=TITLES[m], color=COLORS[m])
    plt.xticks(list(xs), labels_x)
    plt.yscale('log')
    plt.xlabel('Длина фрагмента, слов')
    plt.ylabel('Время, мс (логарифмическая шкала)')
    plt.title('Среднее время распознавания одного текста')
    plt.grid(alpha=.3, axis='y')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'time_by_length.png'), dpi=150)

    # ---------- вывод в консоль ----------
    print(f'Построение профилей: {train_info["train_ms"]} (всего {train_total:.0f} мс)')
    print(f'Извлечение текста из PDF: {result["extract_avg_ms"]} мс на документ')
    for m in methods:
        x = s['methods'][m]
        print(f'{TITLES[m]:16} точность {x["accuracy"]:.3f} ({x["correct"]}/{x["labeled"]}), '
              f'среднее время {x["avg_ms"]} мс')
    print('Фрагменты:')
    for k in bench['lengths']:
        print(f'  {k:>4}: ' + '  '.join(
            f'{TITLES[m]} {bench["table"][m][k]["accuracy"]:.3f}/{bench["table"][m][k]["avg_ms"]}мс'
            for m in methods))


if __name__ == '__main__':
    main()
