"""Рендер схем отчёта из tools/diagrams/*.mmd в results/diagrams/*.png (нужен mmdc — Mermaid CLI)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "results" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)
for src in sorted((ROOT / "diagrams").glob("*.mmd")):
    subprocess.run(["mmdc", "-i", str(src), "-o", str(OUT / (src.stem + ".png")), "-b", "white", "-s", "2.5",
                    "-w", "1100", "-c", str(ROOT / "diagrams" / "mermaid.json")], check=True)
    print(src.stem)
