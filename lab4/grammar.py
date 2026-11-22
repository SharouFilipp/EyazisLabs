from __future__ import annotations

SPACY_MODEL = "en_core_web_sm"

DEP_TO_ROLE = {
    "nsubj": "Subject", "nsubjpass": "Subject (passive)", "dobj": "Object", "pobj": "Object (prepositional)",
    "iobj": "Indirect Object", "attr": "Attribute", "amod": "Attribute (adjective)", "advmod": "Adverbial",
    "root": "Predicate", "ROOT": "Predicate", "acomp": "Adjective Complement", "ccomp": "Clause Complement",
    "aux": "Auxiliary Verb", "det": "Determiner", "prep": "Preposition", "conj": "Conjunct", "cc": "Conjunction",
    "neg": "Negation", "poss": "Possessive", "appos": "Apposition", "nummod": "Numeral modifier",
}
ROLE_RU = {
    "Subject": "подлежащее", "Subject (passive)": "подлежащее (пассив)", "Object": "прямое дополнение",
    "Object (prepositional)": "предложное дополнение", "Indirect Object": "косвенное дополнение",
    "Attribute": "именная часть сказуемого", "Attribute (adjective)": "определение", "Adverbial": "обстоятельство",
    "Predicate": "сказуемое", "Adjective Complement": "именная часть (прил.)", "Clause Complement": "придаточное дополнительное",
    "Auxiliary Verb": "вспомогательный глагол", "Determiner": "определитель", "Preposition": "предлог",
    "Conjunct": "однородный член", "Conjunction": "союз", "Negation": "отрицание", "Possessive": "притяжательное определение",
    "Apposition": "приложение", "Numeral modifier": "числительное",
}
EXTRA_ROLE_RU = {
    "compound": "часть составного слова", "auxpass": "вспомогательный глагол (пассив)", "mark": "подчинительный союз",
    "xcomp": "инфинитивное дополнение", "advcl": "придаточное обстоятельственное", "relcl": "придаточное определительное",
    "acl": "причастный оборот", "prt": "частица фразового глагола", "dative": "косвенное дополнение",
    "expl": "формальное подлежащее", "punct": "знак препинания", "pcomp": "дополнение предлога",
    "npadvmod": "обстоятельство (именное)", "predet": "предопределитель", "case": "показатель падежа",
    "agent": "агенс (by …)", "oprd": "предикатив", "csubj": "подлежащее-предложение", "quantmod": "количественный модификатор",
    "preconj": "часть парного союза", "intj": "междометие", "dep": "связь не определена", "meta": "служебный элемент",
}

MORPH_FEATURES = {
    "Number=Sing": ("number", "singular"), "Number=Plur": ("number", "plural"),
    "Tense=Past": ("tense", "past"), "Tense=Pres": ("tense", "present"),
    "Person=1": ("person", "first"), "Person=2": ("person", "second"), "Person=3": ("person", "third"),
    "Degree=Pos": ("degree", "positive"), "Degree=Cmp": ("degree", "comparative"), "Degree=Sup": ("degree", "superlative"),
    "Voice=Act": ("voice", "active"), "Voice=Pass": ("voice", "passive"),
}
MORPH_RU = {
    "singular": "ед. число", "plural": "мн. число", "past": "прош. время", "present": "наст. время",
    "first": "1-е лицо", "second": "2-е лицо", "third": "3-е лицо", "positive": "положит. степень",
    "comparative": "сравнит. степень", "superlative": "превосх. степень", "active": "действ. залог", "passive": "страд. залог",
}

POS_RU = {
    "NOUN": "существительное", "PROPN": "имя собственное", "VERB": "глагол", "AUX": "вспомогательный глагол",
    "ADJ": "прилагательное", "ADV": "наречие", "ADP": "предлог", "DET": "определитель (артикль)",
    "PRON": "местоимение", "NUM": "числительное", "CCONJ": "сочинительный союз", "SCONJ": "подчинительный союз",
    "PART": "частица", "INTJ": "междометие", "PUNCT": "знак препинания", "SYM": "символ", "X": "другое",
}
TAG_RU = {
    "NN": "существительное, ед. ч.", "NNS": "существительное, мн. ч.", "NNP": "имя собственное, ед. ч.",
    "NNPS": "имя собственное, мн. ч.", "VB": "глагол, инфинитив", "VBD": "глагол, прошедшее время",
    "VBG": "глагол, герундий / причастие наст. вр.", "VBN": "глагол, причастие прош. вр.",
    "VBP": "глагол, наст. вр., не 3-е л. ед. ч.", "VBZ": "глагол, наст. вр., 3-е л. ед. ч.", "MD": "модальный глагол",
    "JJ": "прилагательное", "JJR": "прилагательное, сравнит. степень", "JJS": "прилагательное, превосх. степень",
    "RB": "наречие", "RBR": "наречие, сравнит. степень", "RBS": "наречие, превосх. степень", "IN": "предлог / подчинит. союз",
    "DT": "определитель (артикль)", "PDT": "предопределитель", "PRP": "личное местоимение", "PRP$": "притяжательное местоимение",
    "WDT": "относительное определительное слово", "WP": "относительное местоимение", "WP$": "притяж. относ. местоимение",
    "WRB": "относительное наречие", "CC": "сочинительный союз", "CD": "количественное числительное", "TO": "частица to",
    "RP": "частица (фразовый глагол)", "EX": "формальное there", "POS": "притяжательное 's", "UH": "междометие",
    "FW": "иностранное слово", "SYM": "символ", "LS": "маркер списка", "HYPH": "дефис", "XX": "неизвестно",
    ".": "знак конца предложения", ",": "запятая", ":": "двоеточие / точка с запятой", "``": "открывающая кавычка",
    "''": "закрывающая кавычка", "-LRB-": "открывающая скобка", "-RRB-": "закрывающая скобка", "NFP": "пунктуация", "AFX": "аффикс",
    "ADD": "адрес (e-mail, URL)",
}
GENDER_RU = {"m": "м. р.", "f": "ж. р."}


def extract_morphology_features(token) -> dict:
    features = {"number": set(), "tense": set(), "person": set(), "degree": set(), "voice": set()}
    morph_str = str(token.morph)
    for pattern, (category, value) in MORPH_FEATURES.items():
        if pattern in morph_str:
            features[category].add(value)
    return features


def role_of(token) -> str:
    if token.dep_ == "ROOT" and token.pos_ not in ("VERB", "AUX"):
        return "главное слово (вершина)"
    role = DEP_TO_ROLE.get(token.dep_)
    if role:
        return ROLE_RU.get(role, role)
    return EXTRA_ROLE_RU.get(token.dep_, token.dep_)


def morph_ru(token) -> str:
    feats = extract_morphology_features(token)
    parts = [MORPH_RU[v] for cat in ("number", "tense", "person", "degree", "voice") for v in sorted(feats[cat])]
    return ", ".join(parts)


class LexemeEntry:
    __slots__ = ("lemma", "pos", "tags", "roles", "morph", "forms", "examples", "frequency", "translation")

    def __init__(self, lemma: str, pos: str):
        self.lemma, self.pos = lemma, pos
        self.tags, self.roles, self.morph, self.forms = set(), set(), set(), set()
        self.examples: list[str] = []
        self.frequency = 0
        self.translation = None

    def add_from_token(self, token, sentence_text: str) -> None:
        self.frequency += 1
        self.tags.add(token.tag_)
        self.roles.add(role_of(token))
        m = morph_ru(token)
        if m:
            self.morph.add(m)
        self.forms.add(token.text.lower())
        if sentence_text and sentence_text not in self.examples and len(self.examples) < 3:
            self.examples.append(sentence_text[:150])

    def to_dict(self) -> dict:
        return {"lemma": self.lemma, "pos": self.pos, "pos_ru": POS_RU.get(self.pos, self.pos),
                "tags": sorted(self.tags), "tags_ru": [f"{t} — {TAG_RU.get(t, t)}" for t in sorted(self.tags)],
                "roles": sorted(self.roles), "morph": sorted(self.morph), "forms": sorted(self.forms),
                "examples": self.examples, "frequency": self.frequency, "translation": self.translation}
