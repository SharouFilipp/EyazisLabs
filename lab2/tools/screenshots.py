"""
Скриншоты вкладок интерфейса для отчёта (нужен запущенный сервер).
Используется установленный браузер Google Chrome, отдельная загрузка Chromium не требуется.

Запуск:  uv run python tools/screenshots.py [http://127.0.0.1:8002]
"""

import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'results', 'screens')
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8002'


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        page = browser.new_page(viewport={'width': 1360, 'height': 900}, device_scale_factor=1)
        page.goto(URL)
        page.wait_for_load_state('networkidle')

        page.click('#btn-detect')
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(OUT, '1_detect.png'))
        page.screenshot(path=os.path.join(OUT, '1_detect_full.png'), full_page=True)

        page.click('.tab[data-tab=text]')
        page.click("button:has-text('Пример (франц.)')")
        page.click('#btn-text')
        page.wait_for_timeout(800)
        page.screenshot(path=os.path.join(OUT, '2_text.png'))

        page.click('.tab[data-tab=stats]')
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(OUT, '3_stats.png'), full_page=True)

        page.click('.tab[data-tab=compare]')
        page.fill('#per-doc', '20')
        page.click('#btn-bench')
        page.wait_for_selector('#bench-table table', timeout=60000)
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(OUT, '4_compare.png'), full_page=True)

        page.click('.tab[data-tab=profiles]')
        page.mouse.move(5, 600)
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(OUT, '5_profiles.png'))

        page.click('.tab[data-tab=help]')
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(OUT, '6_help.png'), full_page=True)

        page.click('.tab[data-tab=detect]')
        page.evaluate('viewDoc(16)')
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(OUT, '7_viewer.png'))
        page.evaluate('closeViewer()')

        page.goto(URL + '/api/report?fmt=view')
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(OUT, '8_report.png'))
        browser.close()
    print('Скриншоты сохранены в', OUT)


if __name__ == '__main__':
    main()
