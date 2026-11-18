# benchmark.py
"""
Тест производительности: загружает список URL и замеряет время
на каждом этапе (скачивание, индексация, поиск, метрики).
"""

import time
import requests

SERVER = "http://127.0.0.1:8000"

URLS = [
    # Крупные обзорные статьи — дадут много терминов
    'https://ru.wikipedia.org/wiki/Искусственный_интеллект',
    'https://ru.wikipedia.org/wiki/Машинное_обучение',
    'https://ru.wikipedia.org/wiki/Нейронная_сеть',
    'https://ru.wikipedia.org/wiki/Обработка_естественного_языка',
    'https://ru.wikipedia.org/wiki/Компьютерная_лингвистика',
    'https://ru.wikipedia.org/wiki/Теория_вероятностей',
    'https://ru.wikipedia.org/wiki/Линейная_алгебра',
    'https://ru.wikipedia.org/wiki/Алгоритм',
    'https://ru.wikipedia.org/wiki/Структура_данных',
    'https://ru.wikipedia.org/wiki/База_данных',

    # Статьи по теме ИПС
    'https://ru.wikipedia.org/wiki/Информационный_поиск',
    'https://ru.wikipedia.org/wiki/Векторная_модель',
    'https://ru.wikipedia.org/wiki/TF-IDF',
    'https://ru.wikipedia.org/wiki/Лемматизация',
    'https://ru.wikipedia.org/wiki/Инвертированный_индекс',
    'https://ru.wikipedia.org/wiki/Релевантность',
    'https://ru.wikipedia.org/wiki/Полнотекстовый_поиск',
    'https://ru.wikipedia.org/wiki/Косинусная_мера',

    # Программирование и технологии
    'https://ru.wikipedia.org/wiki/Python',
    'https://ru.wikipedia.org/wiki/PostgreSQL',
    'https://ru.wikipedia.org/wiki/FastAPI',
    'https://ru.wikipedia.org/wiki/JavaScript',
    'https://ru.wikipedia.org/wiki/HTML',
    'https://ru.wikipedia.org/wiki/HTTP',

    # Что-то постороннее — для реалистичных метрик
    'https://ru.wikipedia.org/wiki/Космос',
    'https://ru.wikipedia.org/wiki/История_России',
    'https://ru.wikipedia.org/wiki/Музыка',
]

TEST_QUERIES = [
    "векторная модель поиска",
    "информационный поиск",
    "поиск",
]


def check_server():
    try:
        r = requests.get(SERVER, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def clear_all():
    print("\n[1] Очистка базы...")
    t0 = time.time()
    requests.post(f"{SERVER}/api/documents/clear", timeout=30)
    print(f"    Очищено за {time.time() - t0:.2f} с")


def load_urls():
    print(f"\n[2] Загрузка {len(URLS)} URL...")
    t0 = time.time()
    r = requests.post(
        f"{SERVER}/api/documents/load_urls", json={"urls": URLS}, timeout=600
    )
    elapsed = time.time() - t0
    data = r.json()
    print(f"    Всего времени: {elapsed:.2f} с")
    print(f'    Добавлено:     {len(data.get("added", []))}')
    print(f'    Обновлено:     {len(data.get("updated", []))}')
    print(f'    Ошибок:        {len(data.get("errors", []))}')
    print(f"    Среднее на URL: {elapsed / len(URLS):.2f} с")

    timing = data.get("timing")
    if timing:
        print(f'    Индексация:    {timing["index"]} с')
        print(f"\n    По URL:")
        for item in timing["per_url"]:
            print(
                f'      {item["url"][:65]:65s} load={item["load"]:.2f}s db={item["db"]:.3f}s'
            )

    return elapsed


def stats():
    print("\n[3] Статистика индекса...")
    r = requests.get(f"{SERVER}/api/index/stats", timeout=10)
    s = r.json()
    print(f'    Документов: {s["documents"]}')
    print(f'    Терминов:   {s["terms"]}')
    print(f'    Связей:     {s["links"]}')


def search_timing():
    print("\n[4] Замер поиска...")
    results = []
    for q in TEST_QUERIES:
        t0 = time.time()
        r = requests.post(
            f"{SERVER}/api/search", json={"query": q, "top_k": 10}, timeout=30
        )
        elapsed = (time.time() - t0) * 1000  # мс
        n = len(r.json().get("results", []))
        results.append((q, elapsed, n))
        print(f"    «{q}» — {elapsed:.0f} мс, найдено: {n}")

    avg = sum(x[1] for x in results) / len(results)
    print(f"    Среднее время поиска: {avg:.0f} мс")
    return avg


def main():
    print("=" * 70)
    print("  БЕНЧМАРК ИПС — загрузка Википедии и замер производительности")
    print("=" * 70)

    if not check_server():
        print(f"\n[!] Сервер {SERVER} недоступен. Запусти uvicorn.")
        return

    clear_all()
    t_load = load_urls()
    stats()
    t_search = search_timing()

    print("\n" + "=" * 70)
    print("  ИТОГИ")
    print("=" * 70)
    print(f"  Загрузка {len(URLS)} URL:   {t_load:.2f} с")
    print(f"  Среднее на URL:        {t_load / len(URLS):.2f} с")
    print(f"  Среднее время поиска:  {t_search:.0f} мс")
    print("=" * 70)


if __name__ == "__main__":
    main()
