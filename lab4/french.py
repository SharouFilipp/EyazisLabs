from __future__ import annotations

VOWELS = set("aeiouyàâäéèêëîïôöùûüœæ")
H_ASPIRE = {"héros", "haut", "haute", "hauts", "hautes", "hasard", "haine", "honte", "hache", "hall", "hibou",
            "hiérarchie", "hors", "huit", "huitième", "hangar"}


def starts_with_vowel(word: str) -> bool:
    w = word.lower().lstrip("«( ")
    if not w:
        return False
    if w in H_ASPIRE or w.split(" ")[0] in H_ASPIRE:
        return False
    return w[0] in VOWELS or (w[0] == "h" and len(w) > 1)


_AL_EXC = {"bal", "festival", "carnaval", "chacal", "récital", "régal", "cal", "final", "banal", "fatal", "natal", "naval"}
_AIL_AUX = {"travail", "vitrail", "émail", "corail", "soupirail", "bail", "vantail"}
_OU_X = {"bijou", "caillou", "chou", "genou", "hibou", "joujou", "pou"}
_EU_S = {"pneu", "bleu", "émeu"}


def plural_word(w: str) -> str:
    if not w or w[-1] in "sxz":
        return w
    if w.endswith(("au", "eau")) or (w.endswith("eu") and w not in _EU_S):
        return w + "x"
    if w.endswith("al") and w not in _AL_EXC:
        return w[:-2] + "aux"
    if w in _AIL_AUX:
        return w[:-3] + "aux"
    if w in _OU_X:
        return w + "x"
    return w + "s"


def noun_plural(fr: str, override: str | None = None) -> str:
    if override:
        return override
    parts = fr.split(" ")
    if len(parts) == 1:
        if "-" in fr:
            return "-".join(plural_word(p) for p in fr.split("-"))
        return plural_word(fr)
    if parts[1] in ("de", "d'", "à", "en", "par", "pour") or parts[1].startswith("d'"):
        return " ".join([plural_word(parts[0])] + parts[1:])
    return " ".join(plural_word(p) for p in parts)


def adj_feminine(m: str) -> str:
    if m.endswith("e"):
        return m
    for suf, rep in (("eux", "euse"), ("if", "ive"), ("el", "elle"), ("eil", "eille"), ("ien", "ienne"),
                     ("en", "enne"), ("on", "onne"), ("er", "ère"), ("et", "ette"), ("gu", "guë"),
                     ("teur", "trice"), ("anc", "anche"), ("ul", "ule")):
        if m.endswith(suf):
            return m[: -len(suf)] + rep
    return m + "e"


def adj_plural_m(m: str) -> str:
    if m[-1] in "sx":
        return m
    if m.endswith("al") and m not in _AL_EXC:
        return m[:-2] + "aux"
    if m.endswith("eau"):
        return m + "x"
    return m + "s"


def adj_form(entry_fr: str, extra: dict, gender: str, plural: bool, before_vowel: bool = False) -> str:
    if "inv" in extra:
        return entry_fr
    words = entry_fr.split(" ")
    if len(words) > 1 and words[0] in ("plus", "moins", "très", "le", "la", "les"):
        return " ".join(words[:-1] + [adj_form(words[-1], extra, gender, plural, before_vowel)])
    if gender == "f":
        fem = extra.get("f") or adj_feminine(entry_fr)
        if plural:
            return extra.get("fpl") or (fem if fem.endswith("s") else fem + "s")
        return fem
    if plural:
        return extra.get("pl") or adj_plural_m(entry_fr)
    if before_vowel and extra.get("mv"):
        return extra["mv"]
    return entry_fr


def past_participle_agree(pp: str, gender: str, plural: bool) -> str:
    words = pp.split(" ")
    w = words[0]
    if gender == "f" and not w.endswith("e"):
        w += "e"
    if plural and not w.endswith(("s", "x")):
        w += "s"
    return " ".join([w] + words[1:])


def definite(gender: str, plural: bool) -> str:
    return "les" if plural else ("la" if gender == "f" else "le")


def indefinite(gender: str, plural: bool) -> str:
    return "des" if plural else ("une" if gender == "f" else "un")


def partitive(gender: str) -> str:
    return "de la" if gender == "f" else "du"


def demonstrative(gender: str, plural: bool, next_word: str) -> str:
    if plural:
        return "ces"
    if gender == "f":
        return "cette"
    return "cet" if starts_with_vowel(next_word) else "ce"


POSSESSIVE = {
    (1, False): ("mon", "ma", "mes"), (2, False): ("ton", "ta", "tes"), (3, False): ("son", "sa", "ses"),
    (1, True): ("notre", "notre", "nos"), (2, True): ("votre", "votre", "vos"), (3, True): ("leur", "leur", "leurs"),
}


def possessive(person: int, owner_plural: bool, gender: str, plural: bool, next_word: str) -> str:
    m, f, pl = POSSESSIVE[(person, owner_plural)]
    if plural:
        return pl
    if gender == "f":
        return m if starts_with_vowel(next_word) else f
    return m


IRREG = {
    "être": (["suis", "es", "est", "sommes", "êtes", "sont"], "été", "ser"),
    "avoir": (["ai", "as", "a", "avons", "avez", "ont"], "eu", "aur"),
    "aller": (["vais", "vas", "va", "allons", "allez", "vont"], "allé", "ir"),
    "faire": (["fais", "fais", "fait", "faisons", "faites", "font"], "fait", "fer"),
    "pouvoir": (["peux", "peux", "peut", "pouvons", "pouvez", "peuvent"], "pu", "pourr"),
    "vouloir": (["veux", "veux", "veut", "voulons", "voulez", "veulent"], "voulu", "voudr"),
    "devoir": (["dois", "dois", "doit", "devons", "devez", "doivent"], "dû", "devr"),
    "savoir": (["sais", "sais", "sait", "savons", "savez", "savent"], "su", "saur"),
    "falloir": (["faut", "faut", "faut", "faut", "faut", "faut"], "fallu", "faudr"),
    "valoir": (["vaux", "vaux", "vaut", "valons", "valez", "valent"], "valu", "vaudr"),
    "prendre": (["prends", "prends", "prend", "prenons", "prenez", "prennent"], "pris", "prendr"),
    "mettre": (["mets", "mets", "met", "mettons", "mettez", "mettent"], "mis", "mettr"),
    "venir": (["viens", "viens", "vient", "venons", "venez", "viennent"], "venu", "viendr"),
    "tenir": (["tiens", "tiens", "tient", "tenons", "tenez", "tiennent"], "tenu", "tiendr"),
    "dire": (["dis", "dis", "dit", "disons", "dites", "disent"], "dit", "dir"),
    "lire": (["lis", "lis", "lit", "lisons", "lisez", "lisent"], "lu", "lir"),
    "écrire": (["écris", "écris", "écrit", "écrivons", "écrivez", "écrivent"], "écrit", "écrir"),
    "uire": (["uis", "uis", "uit", "uisons", "uisez", "uisent"], "uit", "uir"),
    "naître": (["nais", "nais", "naît", "naissons", "naissez", "naissent"], "né", "naîtr"),
    "aître": (["ais", "ais", "aît", "aissons", "aissez", "aissent"], "u", "aîtr"),
    "croire": (["crois", "crois", "croit", "croyons", "croyez", "croient"], "cru", "croir"),
    "voir": (["vois", "vois", "voit", "voyons", "voyez", "voient"], "vu", "verr"),
    "cevoir": (["çois", "çois", "çoit", "cevons", "cevez", "çoivent"], "çu", "cevr"),
    "mourir": (["meurs", "meurs", "meurt", "mourons", "mourez", "meurent"], "mort", "mourr"),
    "courir": (["cours", "cours", "court", "courons", "courez", "courent"], "couru", "courr"),
    "vivre": (["vis", "vis", "vit", "vivons", "vivez", "vivent"], "vécu", "vivr"),
    "suivre": (["suis", "suis", "suit", "suivons", "suivez", "suivent"], "suivi", "suivr"),
    "vrir": (["vre", "vres", "vre", "vrons", "vrez", "vrent"], "vert", "vrir"),
    "frir": (["fre", "fres", "fre", "frons", "frez", "frent"], "fert", "frir"),
    "battre": (["bats", "bats", "bat", "battons", "battez", "battent"], "battu", "battr"),
    "soudre": (["sous", "sous", "sout", "solvons", "solvez", "solvent"], "solu", "soudr"),
    "traire": (["trais", "trais", "trait", "trayons", "trayez", "traient"], "trait", "trair"),
    "eindre": (["eins", "eins", "eint", "eignons", "eignez", "eignent"], "eint", "eindr"),
    "aindre": (["ains", "ains", "aint", "aignons", "aignez", "aignent"], "aint", "aindr"),
    "clure": (["clus", "clus", "clut", "cluons", "cluez", "cluent"], "clus", "clur"),
    "rire": (["ris", "ris", "rit", "rions", "riez", "rient"], "ri", "rir"),
    "plaire": (["plais", "plais", "plaît", "plaisons", "plaisez", "plaisent"], "plu", "plair"),
    "boire": (["bois", "bois", "boit", "buvons", "buvez", "boivent"], "bu", "boir"),
}
SENTIR = {"sentir": "sen", "ressentir": "ressen", "partir": "par", "repartir": "repar", "sortir": "sor",
          "servir": "ser", "mentir": "men", "dormir": "dor", "consentir": "consen", "pressentir": "pressen"}
SUFFIX_BASES = ["prendre", "mettre", "venir", "tenir", "écrire", "crire", "cevoir", "aître",
                "battre", "soudre", "traire", "eindre", "aindre", "clure", "suivre", "vivre", "vrir", "frir",
                "uire", "voir", "dire", "lire"]
NO_SUFFIX = {"devoir", "pouvoir", "savoir", "vouloir", "valoir", "falloir", "avoir", "pourvoir"}
ETRE_VERBS = {"aller", "venir", "devenir", "revenir", "arriver", "partir", "entrer", "rentrer", "sortir", "monter",
              "descendre", "naître", "mourir", "rester", "tomber", "retourner", "apparaître"}
SECOND_GROUP_EXC = {"sentir", "partir", "sortir", "servir", "mentir", "dormir", "courir", "mourir", "venir", "tenir",
                    "ouvrir", "offrir", "souffrir", "couvrir", "découvrir", "cueillir", "fuir", "acquérir", "ressentir"}
FUT_SPECIAL = {"envoyer": "enverr", "renvoyer": "renverr", "appeler": "appeller", "rappeler": "rappeller",
               "rejeter": "rejetter", "jeter": "jetter", "acheter": "achèter", "mener": "mèner", "amener": "amèner",
               "lever": "lèver", "enlever": "enlèver", "essayer": "essaier", "employer": "emploier",
               "nettoyer": "nettoier"}


def _base_of(inf: str) -> tuple[str, str] | None:
    if inf in IRREG:
        return "", inf
    if inf in NO_SUFFIX:
        return None
    for b in SUFFIX_BASES:
        if inf.endswith(b) and inf != b:
            return inf[: -len(b)], b
    return None


IRREG["crire"] = (["cris", "cris", "crit", "crivons", "crivez", "crivent"], "crit", "crir")


def _first_group_present(inf: str) -> list[str]:
    stem = inf[:-2]
    forms = [stem + e for e in ("e", "es", "e", "ons", "ez", "ent")]
    if stem.endswith("c"):
        forms[3] = stem[:-1] + "çons"
    if stem.endswith("g"):
        forms[3] = stem + "eons"
    if inf in ("appeler", "rappeler", "rejeter", "jeter", "épeler"):
        dbl = stem + stem[-1]
        for i in (0, 1, 2, 5):
            forms[i] = dbl + ("e", "es", "e", "", "", "ent")[i]
    elif len(stem) >= 2 and stem[-2] in "eé" and stem[-1] not in "aeiouy" and inf not in ("créer",):
        i_e = len(stem) - 2
        st = stem[:i_e] + "è" + stem[i_e + 1:]
        for i in (0, 1, 2, 5):
            forms[i] = st + ("e", "es", "e", "", "", "ent")[i]
    elif stem.endswith(("oy", "uy", "ay")):
        st = stem[:-1] + "i"
        for i in (0, 1, 2, 5):
            forms[i] = st + ("e", "es", "e", "", "", "ent")[i]
    return forms


def present_forms(inf: str) -> list[str]:
    b = _base_of(inf)
    if b:
        prefix, base = b
        return [prefix + f for f in IRREG[base][0]]
    if inf in SENTIR:
        s = SENTIR[inf]
        last = inf[len(s)]
        return [s + "s", s + "s", s + "t", s + last + "ons", s + last + "ez", s + last + "ent"]
    if inf.endswith("er"):
        return _first_group_present(inf)
    if inf.endswith("ir") and inf not in SECOND_GROUP_EXC:
        st = inf[:-2]
        return [st + "is", st + "is", st + "it", st + "issons", st + "issez", st + "issent"]
    if inf.endswith("re"):
        st = inf[:-2]
        return [st + "s", st + "s", st, st + "ons", st + "ez", st + "ent"]
    if inf.endswith("ir"):
        st = inf[:-2]
        return [st + "s", st + "s", st + "t", st + "ons", st + "ez", st + "ent"]
    return [inf] * 6


def past_participle(inf: str) -> str:
    b = _base_of(inf)
    if b:
        prefix, base = b
        pp = IRREG[base][1]
        if base == "aître":
            return prefix + pp
        return prefix + pp
    if inf in SENTIR:
        return inf[:-2] + "i"
    if inf.endswith("er"):
        return inf[:-2] + "é"
    if inf.endswith("ir"):
        return inf[:-2] + "i"
    if inf.endswith("re"):
        return inf[:-2] + "u"
    return inf


def future_stem(inf: str) -> str:
    b = _base_of(inf)
    if b:
        prefix, base = b
        return prefix + IRREG[base][2]
    if inf in FUT_SPECIAL:
        return FUT_SPECIAL[inf]
    if inf.endswith("re"):
        return inf[:-1]
    return inf


def imperfect_stem(inf: str) -> str:
    if inf == "être":
        return "ét"
    nous = present_forms(inf)[3]
    st = nous[:-3] if nous.endswith("ons") else nous
    if inf.endswith("cer") and st.endswith("ç"):
        return st
    if inf.endswith("ger") and st.endswith("ge"):
        return st
    return st


def present_participle(inf: str) -> str:
    if inf == "être":
        return "étant"
    if inf == "avoir":
        return "ayant"
    if inf == "savoir":
        return "sachant"
    return imperfect_stem(inf) + "ant"


IMPF_END = ["ais", "ais", "ait", "ions", "iez", "aient"]
FUT_END = ["ai", "as", "a", "ons", "ez", "ont"]
COND_END = IMPF_END


def _idx(person: int, plural: bool) -> int:
    return (person - 1) + (3 if plural else 0)


def finite(inf: str, tense: str, person: int = 3, plural: bool = False) -> str:
    i = _idx(person, plural)
    if tense == "pres":
        return present_forms(inf)[i]
    if tense == "impf":
        st = imperfect_stem(inf)
        end = IMPF_END[i]
        if st.endswith("ç") and end[0] == "i":
            st = st[:-1] + "c"
        if st.endswith("ge") and end[0] == "i":
            st = st[:-1]
        return st + end
    if tense == "fut":
        return future_stem(inf) + FUT_END[i]
    if tense == "cond":
        return future_stem(inf) + COND_END[i]
    raise ValueError(tense)


REFLEXIVE = {(1, False): "me", (2, False): "te", (3, False): "se", (1, True): "nous", (2, True): "vous", (3, True): "se"}


def split_verb(fr: str) -> tuple[bool, str, str]:
    refl = False
    if fr.startswith("se "):
        refl, fr = True, fr[3:]
    elif fr.startswith("s'"):
        refl, fr = True, fr[2:]
    head, _, rest = fr.partition(" ")
    return refl, head, rest


def uses_etre(inf: str, reflexive: bool) -> bool:
    return reflexive or inf in ETRE_VERBS


def conjugate(fr: str, tense: str, person: int = 3, plural: bool = False, gender: str = "m",
              neg: str | None = None, clitics: list[str] | None = None, aux_override: str | None = None) -> list[str]:
    refl, inf, rest = split_verb(fr)
    clitics = list(clitics or [])
    pre = []
    if refl:
        pre.append(REFLEXIVE[(person, plural)])
    pre += clitics
    tail = [rest] if rest else []
    if tense in ("pc", "pqp"):
        aux = aux_override or ("être" if uses_etre(inf, refl) else "avoir")
        aux_form = finite(aux, "pres" if tense == "pc" else "impf", person, plural)
        pp = past_participle(inf)
        if aux == "être":
            pp = past_participle_agree(pp, gender, plural)
        core = [aux_form] + ([neg] if neg else []) + [pp]
        return (["ne"] if neg else []) + pre + core + tail
    if tense == "inf":
        if refl:
            pre[0] = REFLEXIVE[(person, plural)]
        return (["ne", neg] if neg else []) + pre + [inf] + tail
    if tense == "ppr":
        return (["ne"] if neg else []) + pre + [present_participle(inf)] + ([neg] if neg else []) + tail
    if tense == "pp":
        return [past_participle_agree(past_participle(inf), gender, plural)] + tail
    form = finite(inf, tense, person, plural)
    return (["ne"] if neg else []) + pre + [form] + ([neg] if neg else []) + tail


CONTRACT = {("à", "le"): "au", ("à", "les"): "aux", ("de", "le"): "du", ("de", "les"): "des"}
ELIDE = {"le": "l'", "la": "l'", "de": "d'", "que": "qu'", "ne": "n'", "je": "j'", "me": "m'", "te": "t'",
         "se": "s'", "ce": "c'", "jusque": "jusqu'", "lorsque": "lorsqu'", "puisque": "puisqu'", "si": "s'"}


def finalize(words: list[dict]) -> str:
    out: list[dict] = []
    words = [w for w in words if w.get("t")]
    for wi, w in enumerate(words):
        if out and w.get("k") == "art" and out[-1]["t"] in ("à", "de"):
            pair = (out[-1]["t"], w["t"])
            nxt_word = words[wi + 1]["t"] if wi + 1 < len(words) else ""
            if pair in CONTRACT and not (w["t"] == "le" and starts_with_vowel(nxt_word)):
                out[-1] = {**out[-1], "t": CONTRACT[pair]}
                continue
            if out[-1]["t"] == "de" and w["t"] in ("des", "de"):
                continue
        if out and w.get("k") == "art" and w["t"] == "des" and out[-1]["t"] == "de" and out[-1].get("k") == "art":
            continue
        if w.get("preadj") and out and out[-1].get("k") == "art" and out[-1]["t"] == "des":
            out[-1] = {**out[-1], "t": "de"}
        out.append(dict(w))
    for i in range(len(out) - 1):
        t = out[i]["t"]
        nxt = out[i + 1]["t"]
        if out[i].get("k") == "punct":
            continue
        if t.lower() in ELIDE and starts_with_vowel(nxt):
            if t.lower() == "si" and not nxt.lower().startswith(("il", "ils")):
                continue
            if t.lower() == "ce" and not nxt.lower().startswith(("est", "était", "en")):
                continue
            if t.lower() in ("le", "la") and out[i + 1].get("k") == "punct":
                continue
            el = ELIDE[t.lower()]
            out[i]["t"] = el if t.islower() else el[0].upper() + el[1:]
            out[i]["glue"] = True
    s = ""
    for i, w in enumerate(out):
        t = w["t"]
        if i == 0:
            s = t
            continue
        prev = out[i - 1]
        if w.get("k") == "punct":
            if t in (";", ":", "!", "?"):
                s += " " + t
            elif t in ("«",):
                s += " " + t + " "
                w["open"] = True
            elif t in ("»",):
                s += " " + t
            elif t in ("(", "["):
                s += " " + t
                w["open"] = True
            else:
                s += t
            continue
        if prev.get("glue") or prev.get("open") or s.endswith(("'", "’")):
            s += t
        else:
            s += " " + t
    return s
