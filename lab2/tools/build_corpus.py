"""
Формирование обучающего набора и тестовой коллекции из статей Википедии.

  corpus/train/en.txt, corpus/train/fr.txt — обучающие тексты (по ~100 КБ на язык);
  corpus/test/*.pdf                         — тестовые документы, по одной странице A4;
  corpus/test/labels.json                   — эталонный язык каждого тестового документа.

Запуск:  uv run python tools/build_corpus.py
"""

import json
import os
import re
import sys
import time
import unicodedata

import requests
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN_DIR = os.path.join(ROOT, 'corpus', 'train')
TEST_DIR = os.path.join(ROOT, 'corpus', 'test')

HEADERS = {'User-Agent': 'EYZIS-lab2/1.0 (BSUIR student lab; language identification)'}

TRAIN_LIMIT_BYTES = 100 * 1024     # размер обучающего текста одного языка
PAGE_CHARS = 2600                  # объём текста одной страницы A4 (шрифт 11 pt)

TRAIN_ARTICLES = {
    'en': ['Language', 'History of Europe', 'Ocean', 'Music', 'Mathematics',
           'Agriculture', 'Literature', 'Computer', 'Medicine', 'Architecture'],
    'fr': ['Langage', "Histoire de l'Europe", 'Océan', 'Musique', 'Mathématiques',
           'Agriculture', 'Littérature', 'Ordinateur', 'Médecine', 'Architecture'],
}

# Темы тестовых документов не пересекаются с обучающими; в обоих языках
# взяты одни и те же темы, чтобы имена собственные не подсказывали язык.
TEST_ARTICLES = {
    'en': ['Photosynthesis', 'Volcano', 'Jazz', 'Bicycle', 'Chess', 'Coffee',
           'Olympic Games', 'Moon', 'Western honey bee', 'Paris', 'Renaissance',
           'Internet', 'Association football', 'Chocolate', 'Rail transport'],
    'fr': ['Photosynthèse', 'Volcan', 'Jazz', 'Bicyclette', 'Échecs', 'Café',
           'Jeux olympiques', 'Lune', 'Abeille domestique', 'Londres', 'Renaissance',
           'Internet', 'Football', 'Chocolat', 'Transport ferroviaire'],
}

STOP_SECTIONS = {
    'en': ('See also', 'References', 'Notes', 'Further reading', 'External links', 'Bibliography'),
    'fr': ('Notes et références', 'Voir aussi', 'Annexes', 'Bibliographie', 'Liens externes', 'Articles connexes'),
}


def fetch_article(lang: str, title: str) -> str:
    for attempt in range(5):
        time.sleep(1.5)  # Википедия ограничивает частоту запросов (HTTP 429)
        resp = requests.get(
            f'https://{lang}.wikipedia.org/w/api.php',
            params={'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                    'redirects': 1, 'titles': title, 'format': 'json'},
            headers=HEADERS, timeout=30,
        )
        if resp.status_code != 429:
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    pages = resp.json()['query']['pages']
    page = next(iter(pages.values()))
    if 'extract' not in page:
        raise RuntimeError(f'статья не найдена: {lang}:{title}')
    return page['extract']


def clean(text: str, lang: str) -> str:
    """Удаляет служебные разделы, заголовки и формулы, оставляет связный текст."""
    out = []
    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'^=+\s*(.*?)\s*=+$', line)
        if m:
            if m.group(1) in STOP_SECTIONS[lang]:
                break
            continue
        if not line or '\\displaystyle' in line or len(line) < 40:
            continue
        out.append(re.sub(r'\s+', ' ', line))
    return '\n'.join(out)


def cut_to_size(text: str, limit: int) -> str:
    """Обрезает текст по границе предложения так, чтобы он не превышал limit символов."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind('. '), cut.rfind('.\n'))
    return cut[:end + 1] if end > limit // 2 else cut


def build_train():
    os.makedirs(TRAIN_DIR, exist_ok=True)
    for lang, titles in TRAIN_ARTICLES.items():
        # каждая статья даёт равную долю обучающего текста — набор тематически разнообразен
        per_article = TRAIN_LIMIT_BYTES // len(titles) + 512
        parts = []
        for title in titles:
            body = cut_to_size(clean(fetch_article(lang, title), lang), per_article)
            parts.append(body)
            print(f'  train {lang}: {title} ({len(body)} симв.)')
        text = '\n'.join(parts).encode('utf-8')[:TRAIN_LIMIT_BYTES].decode('utf-8', 'ignore')
        text = text[:text.rfind('.') + 1]
        with open(os.path.join(TRAIN_DIR, f'{lang}.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'  => {lang}.txt: {len(text.encode("utf-8")) / 1024:.1f} КБ')


def make_pdf(path: str, title: str, text: str):
    doc = SimpleDocTemplate(path, pagesize=A4, title=title,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    h = ParagraphStyle('h', fontName='Arial-Bold', fontSize=15, leading=19, spaceAfter=8)
    p = ParagraphStyle('p', fontName='Arial', fontSize=11, leading=15, spaceAfter=6, alignment=4)
    story = [Paragraph(title, h), Spacer(1, 4)]
    for para in text.split('\n'):
        story.append(Paragraph(para.replace('&', '&amp;').replace('<', '&lt;'), p))
    doc.build(story)


def safe_name(title: str) -> str:
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]+', '_', ascii_title).strip('_')


def build_test():
    os.makedirs(TEST_DIR, exist_ok=True)
    fonts = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
    pdfmetrics.registerFont(TTFont('Arial', os.path.join(fonts, 'arial.ttf')))
    pdfmetrics.registerFont(TTFont('Arial-Bold', os.path.join(fonts, 'arialbd.ttf')))

    labels = {}
    for lang, titles in TEST_ARTICLES.items():
        for i, title in enumerate(titles, 1):
            body = cut_to_size(clean(fetch_article(lang, title), lang), PAGE_CHARS)
            name = f'{lang}_{i:02d}_{safe_name(title)}.pdf'
            make_pdf(os.path.join(TEST_DIR, name), title, body)
            labels[name] = {'lang': lang, 'title': title, 'chars': len(body),
                            'source': f'https://{lang}.wikipedia.org/wiki/{title.replace(" ", "_")}'}
            print(f'  test {name}: {len(body)} симв.')

    with open(os.path.join(TEST_DIR, 'labels.json'), 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('all', 'train'):
        print('Обучающий набор:')
        build_train()
    if what in ('all', 'test'):
        print('Тестовая коллекция:')
        build_test()
