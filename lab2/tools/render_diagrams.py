"""
Рендер схем из docs/diagrams/*.mmd (Mermaid) в PNG с помощью браузера Chrome.

Запуск:  uv run python tools/render_diagrams.py
"""

import glob
import html
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAMS = os.path.join(ROOT, 'docs', 'diagrams')

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>body{margin:0;background:#fff;font-family:'Segoe UI',Arial} #d{display:inline-block;padding:16px}</style>
</head><body><div id="d"><pre class="mermaid">%s</pre></div>
<script>
mermaid.initialize({startOnLoad:false, theme:'neutral', fontFamily:'Segoe UI, Arial', fontSize:15,
                    flowchart:{htmlLabels:true, curve:'basis'}});
mermaid.run().then(() => document.body.dataset.done = '1');
</script></body></html>"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        page = browser.new_page(device_scale_factor=2, viewport={'width': 1600, 'height': 1200})
        for src in sorted(glob.glob(os.path.join(DIAGRAMS, '*.mmd'))):
            with open(src, encoding='utf-8') as f:
                page.set_content(PAGE % html.escape(f.read()))
            page.wait_for_selector('body[data-done="1"]', timeout=30000)
            out = src[:-4] + '.png'
            page.locator('#d').screenshot(path=out)
            print('  ', os.path.basename(out))
        browser.close()


if __name__ == '__main__':
    main()
