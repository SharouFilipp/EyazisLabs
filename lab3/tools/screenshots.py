"""Скриншоты интерфейса для отчёта (сервер должен быть запущен на порту 8003).

Запуск: uv run python tools/screenshots.py  (нужен установленный браузер Playwright)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8003"
OUT = Path(__file__).resolve().parent.parent / "results" / "screens"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1.5)
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))

        def shot(name, full=True, clip=None):
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full, clip=clip)

        page.goto(URL + "/#docs"); page.wait_for_selector("#doc-table tbody tr")
        shot("01_documents")
        page.click("#doc-table tbody tr:nth-child(2) >> text=Реферат")
        page.wait_for_selector("#sum-body .summary-list")
        shot("02_summary")
        page.evaluate("setMethod('ostis')"); page.wait_for_selector("#sum-body code")
        shot("02b_summary_ostis")
        page.evaluate("setMethod('extraction')"); page.wait_for_timeout(300)
        page.evaluate("showTab('text')"); page.wait_for_timeout(400)
        page.select_option("#free-method", "ostis")
        page.click("text=Пример (it)"); page.wait_for_selector("#free-out .summary-list")
        shot("03_text")
        page.evaluate("showTab('eval')"); page.wait_for_selector("#eval-docs table")
        shot("04_eval")
        page.evaluate("showTab('kb')"); page.wait_for_selector("#scg svg")
        page.select_option("#kb-doc", label=page.eval_on_selector(
            "#kb-doc", "el => [...el.options].find(o => o.text.startsWith('it_lit_01')).text"))
        page.wait_for_timeout(600)
        page.locator("#tab-kb .card").first.screenshot(path=str(OUT / "05_kb.png"))
        page.select_option("#kb-method", "ostis"); page.wait_for_timeout(700)
        page.locator("#tab-kb .card").first.screenshot(path=str(OUT / "05c_kb_ostis.png"))
        page.evaluate("document.querySelector('#scs').scrollTop = 0")
        page.locator("#tab-kb .card").nth(1).screenshot(path=str(OUT / "05b_kb_scs.png"))
        page.fill("#kb-q", "chiave"); page.wait_for_timeout(300)
        page.locator("#tab-kb .card").nth(2).screenshot(path=str(OUT / "05d_kb_concepts.png"))
        page.evaluate("showTab('help')"); page.wait_for_timeout(400)
        shot("06_help")
        page.evaluate("showTab('docs')")
        page.click("#doc-table tbody tr:nth-child(9) >> text=Текст"); page.wait_for_selector("#modal.open")
        shot("07_text_modal", full=False)
        first = page.evaluate("docs[0].id")
        page.goto(URL + f"/api/report.html?ids={first}&download=0"); page.wait_for_timeout(300)
        shot("08_report")
        b.close()
    print("ошибки консоли:", errors or "нет")


if __name__ == "__main__":
    main()
