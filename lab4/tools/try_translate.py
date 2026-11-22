import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spacy
from lexicon import Lexicon
from transfer import Translator

nlp = spacy.load("en_core_web_sm")
tr = Translator(nlp, Lexicon.from_seed())
for f in sys.argv[1:]:
    text = Path(f).read_text(encoding="utf-8") if Path(f).exists() else f
    mode = "direct" if "--direct" in sys.argv else "transfer"
    r = tr.translate(text, mode)
    for s in r["sentences"]:
        print("EN:", s["en"])
        print("FR:", s["fr"], ("   [?] " + ", ".join(s["unknown"])) if s["unknown"] else "")
    print(r["stats"], r["domain"], {k: round(v, 1) for k, v in r["time_ms"].items()})
