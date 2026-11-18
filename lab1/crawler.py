import hashlib
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from newspaper import Article

    HAS_NEWSPAPER = True
except ImportError:
    HAS_NEWSPAPER = False
    print("newspaper3k не установлен, используется только BeautifulSoup")


class Crawler:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    TIMEOUT = 20
    MIN_TEXT_LEN = 100

    def fetch(self, url: str):
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"[!] fetch {url}: {e}")
            return None

    def _parse_newspaper(self, url: str):
        if not HAS_NEWSPAPER:
            return None
        try:
            article = Article(url, language="ru")
            article.download()
            article.parse()

            title = (article.title or "").strip()
            text = (article.text or "").strip()
            text = re.sub(r"\s+", " ", text)

            if len(text) < self.MIN_TEXT_LEN:
                return None

            return title, text
        except Exception as e:
            print(f"[!] newspaper {url}: {e}")
            return None

    def _parse_bs4(self, html: str, url: str):
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "header",
                "footer",
                "aside",
                "noscript",
                "form",
                "iframe",
            ]
        ):
            tag.decompose()

        title = soup.title.get_text(strip=True) if soup.title else url

        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < self.MIN_TEXT_LEN:
            return None

        return title, text

    def load(self, url: str):
        title, text = None, None

        result = self._parse_newspaper(url)
        if result:
            title, text = result
            print(f"  [newspaper] {url} → {len(text)} символов")

        if not text:
            html = self.fetch(url)
            if not html:
                return None
            result = self._parse_bs4(html, url)
            if not result:
                print(f"[!] Не удалось извлечь текст: {url}")
                return None
            title, text = result
            print(f"  [bs4] {url} → {len(text)} символов")

        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        host = urlparse(url).netloc.replace(".", "_")[:30]
        filename = f"url_{host}_{h}.txt"

        return filename, title, text, url