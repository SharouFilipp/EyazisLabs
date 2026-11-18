"""Упрощённая sc-память: хранение базы знаний OSTIS в виде семантической сети
и разбор текстов на языке SCs.

Поддерживается подмножество SCs, используемое в базах знаний ostis-web-platform:
    подлежащее
    <- класс;                         дуга принадлежности из класса в элемент
    -> rrel_1: элемент;               дуга принадлежности с ролевым атрибутом
    => nrel_отношение: элемент;       общая (парная) дуга, принадлежащая отношению
    <= nrel_отношение: элемент;;      обратная общая дуга
    [содержимое] (* <- lang_fr;; *)   sc-ссылка и вложенное высказывание о ней
Комментарии начинаются с «//». Каждый идентификатор — один sc-узел; каждая
квадратная скобка — новая sc-ссылка. Дуги хранятся как sc-элементы с типом,
началом, концом и атрибутами (ролевыми или неролевыми отношениями).
"""
import re
from collections import defaultdict
from pathlib import Path

TOKEN_RE = re.compile(r"""
    (?P<comment>//[^\n]*)
  | (?P<link>\[(?:\\.|[^\]\\])*\])
  | (?P<open>\(\*)
  | (?P<close>\*\))
  | (?P<conn><-|->|=>|<=)
  | (?P<end>;;)
  | (?P<semi>;)
  | (?P<colon>:)
  | (?P<idtf>\.{0,2}[A-Za-z_][A-Za-z0-9_]*)
  | (?P<ws>\s+)
""", re.VERBOSE)


class SCsSyntaxError(Exception):
    pass


class ScMemory:
    def __init__(self):
        self.elements = []                  # [{"type": "node"|"link"|"arc", ...}]
        self.by_idtf = {}                   # системный идентификатор → адрес элемента
        self.out = defaultdict(list)        # адрес → исходящие дуги
        self.inc = defaultdict(list)        # адрес → входящие дуги

    # ---------------------------------------------------------------- создание элементов
    def node(self, idtf: str) -> int:
        if idtf not in self.by_idtf:
            self.elements.append({"type": "node", "idtf": idtf})
            self.by_idtf[idtf] = len(self.elements) - 1
        return self.by_idtf[idtf]

    def link(self, content: str) -> int:
        self.elements.append({"type": "link", "content": content})
        return len(self.elements) - 1

    def arc(self, kind: str, src: int, trg: int, attrs=()) -> int:
        """kind: 'access' — дуга принадлежности, 'common' — общая дуга (пара)."""
        self.elements.append({"type": "arc", "kind": kind, "src": src, "trg": trg, "attrs": list(attrs)})
        a = len(self.elements) - 1
        self.out[src].append(a)
        self.inc[trg].append(a)
        # атрибут — дуга принадлежности из узла отношения в саму дугу
        for r in attrs:
            self.elements.append({"type": "arc", "kind": "access", "src": r, "trg": a, "attrs": []})
            self.inc[a].append(len(self.elements) - 1)
            self.out[r].append(len(self.elements) - 1)
        return a

    # ---------------------------------------------------------------- разбор SCs
    def load_scs(self, text: str, source: str = "") -> int:
        tokens = []
        for m in TOKEN_RE.finditer(text):
            kind = m.lastgroup
            if kind in ("ws", "comment"):
                continue
            tokens.append((kind, m.group()))
        pos = 0
        n_sent = 0

        def peek():
            return tokens[pos] if pos < len(tokens) else (None, None)

        def element():
            nonlocal pos
            kind, val = peek()
            if kind == "idtf":
                pos += 1
                return self.node(val)
            if kind == "link":
                pos += 1
                content = re.sub(r"\\(.)", r"\1", val[1:-1])
                return self.link(content)
            raise SCsSyntaxError(f"{source}: ожидался элемент, получено {val!r} (лексема {pos})")

        def tails(subject):
            """Последовательность «связка [атрибуты:] элемент [(* ... *)]», разделённая «;», до «;;»."""
            nonlocal pos
            while True:
                kind, conn = peek()
                if kind != "conn":
                    raise SCsSyntaxError(f"{source}: ожидалась связка, получено {conn!r} (лексема {pos})")
                pos += 1
                attrs = []
                while peek()[0] == "idtf" and pos + 1 < len(tokens) and tokens[pos + 1][0] == "colon":
                    attrs.append(self.node(tokens[pos][1]))
                    pos += 2
                obj = element()
                if peek()[0] == "open":            # вложенное высказывание об объекте
                    pos += 1
                    while peek()[0] != "close":
                        tails(obj)
                    pos += 1
                if conn == "->":
                    self.arc("access", subject, obj, attrs)
                elif conn == "<-":
                    self.arc("access", obj, subject, attrs)
                elif conn == "=>":
                    self.arc("common", subject, obj, attrs)
                else:
                    self.arc("common", obj, subject, attrs)
                kind, _ = peek()
                pos += 1
                if kind == "end":
                    return
                if kind != "semi":
                    raise SCsSyntaxError(f"{source}: ожидалось «;» или «;;» (лексема {pos})")

        while pos < len(tokens):
            subj = element()
            tails(subj)
            n_sent += 1
        return n_sent

    def load_dir(self, path: Path) -> dict:
        stats = {}
        for f in sorted(Path(path).glob("*.scs")):
            stats[f.name] = self.load_scs(f.read_text(encoding="utf-8"), f.name)
        return stats

    # ---------------------------------------------------------------- поиск
    def idtf_of(self, addr: int) -> str | None:
        return self.elements[addr].get("idtf")

    def _has_attr(self, arc: int, rel: str) -> bool:
        r = self.by_idtf.get(rel)
        return r is not None and r in self.elements[arc]["attrs"]

    def members(self, cls: str) -> list[int]:
        """Элементы, в которые ведут дуги принадлежности из класса cls (без атрибутов)."""
        c = self.by_idtf.get(cls)
        if c is None:
            return []
        return [self.elements[a]["trg"] for a in self.out[c]
                if self.elements[a]["type"] == "arc" and self.elements[a]["kind"] == "access"
                and not self.elements[a]["attrs"] and self.elements[self.elements[a]["trg"]]["type"] != "arc"]

    def classes_of(self, addr: int) -> list[str]:
        return [self.idtf_of(self.elements[a]["src"]) for a in self.inc[addr]
                if self.elements[a]["kind"] == "access" and not self.elements[a]["attrs"]]

    def related(self, addr: int, rel: str, direction: str = "out") -> list[int]:
        """Элементы, связанные с addr общей дугой, принадлежащей отношению rel."""
        res = []
        arcs = self.out[addr] if direction == "out" else self.inc[addr]
        for a in arcs:
            e = self.elements[a]
            if e["kind"] == "common" and self._has_attr(a, rel):
                res.append(e["trg"] if direction == "out" else e["src"])
        return res

    def identifiers(self, addr: int, lang: str, rels=("nrel_main_idtf", "nrel_idtf")) -> list[str]:
        """Содержимое sc-ссылок-идентификаторов элемента на заданном языке."""
        out = []
        for rel in rels:
            for l in self.related(addr, rel):
                if self.elements[l]["type"] == "link" and f"lang_{lang}" in self.classes_of(l):
                    out.append(self.elements[l]["content"])
        return out

    def stats(self) -> dict:
        c = defaultdict(int)
        for e in self.elements:
            c[e["type"] if e["type"] != "arc" else "arc_" + e["kind"]] += 1
        return {"nodes": c["node"], "links": c["link"], "access_arcs": c["arc_access"],
                "common_arcs": c["arc_common"], "total": len(self.elements)}
