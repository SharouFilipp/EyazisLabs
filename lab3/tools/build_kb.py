"""Формирование базы знаний OSTIS (kb/*.scs) из таблиц понятий kb/src/domain_*.txt.

Каждое понятие становится sc-узлом класса с основным идентификатором на русском
языке, идентификаторами на французском и итальянском (nrel_idtf), отношением
включения в родительское понятие (nrel_inclusion) и ассоциативными связями
(nrel_related); понятие входит в структуру предметной области.

Запуск: uv run python tools/build_kb.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ostis  # noqa: E402

DOMAINS = {
    "domain_cs": ("subject_domain_computer_science", "Предметная область computer science",
                  "concept_scientific_article_computer_science"),
    "domain_lit": ("subject_domain_literature", "Предметная область литературы", "concept_literary_essay"),
}


def parse(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sid, ru, fr, it, parent, rel = [x.strip() for x in line.split("|")]
        items.append({"id": sid, "ru": ru, "fr": [x.strip() for x in fr.split(";") if x.strip()],
                      "it": [x.strip() for x in it.split(";") if x.strip()], "parent": parent,
                      "related": [x.strip() for x in rel.split(",") if x.strip()]})
    return items


def to_scs(name: str, items: list[dict]) -> str:
    sd, title, doc_class = DOMAINS[name]
    ids = {i["id"] for i in items}
    out = [f"// ===== {title}: {len(items)} понятий (сформировано tools/build_kb.py) =====",
           f"{sd}\n<- sc_node_struct;\n<- subject_domain;\n=> nrel_main_idtf: [{title}] (* <- lang_ru;; *);\n"
           f"=> nrel_document_class: {doc_class};;\n"]
    for i in items:
        lines = [i["id"], "<- sc_node_class;", f"<- {sd};",
                 f"=> nrel_main_idtf: {ostis.scs_string(i['ru'])} (* <- lang_ru;; *);"]
        for lang in ("fr", "it"):
            for k, v in enumerate(i[lang]):
                rel = "nrel_main_idtf" if k == 0 else "nrel_idtf"
                lines.append(f"=> {rel}: {ostis.scs_string(v)} (* <- lang_{lang};; *);")
        if i["parent"]:
            assert i["parent"] in ids, f"{i['id']}: неизвестный родитель {i['parent']}"
            lines.append(f"<= nrel_inclusion: {i['parent']};")
        for r in i["related"]:
            assert r in ids, f"{i['id']}: неизвестное связанное понятие {r}"
            lines.append(f"=> nrel_related: {r};")
        lines[-1] = lines[-1][:-1] + ";;"
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


def main():
    kb = ROOT / "kb"
    (kb / "ontology_summarization.scs").write_text(ostis.ONTOLOGY, encoding="utf-8")
    for name in DOMAINS:
        items = parse(kb / "src" / f"{name}.txt")
        (kb / f"{name}.scs").write_text(to_scs(name, items), encoding="utf-8")
        print(name, len(items), "понятий")


if __name__ == "__main__":
    main()
