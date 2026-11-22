import re
from typing import Tuple

from pypdf import PdfReader

CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def extract_text(path: str) -> Tuple[str, int, str]:
    reader = PdfReader(path)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    text = CONTROL_RE.sub(' ', text)
    title = ''
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title)
    return text.strip(), len(reader.pages), title
