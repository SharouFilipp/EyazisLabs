import re
import unicodedata

LANG_NODE = {"fr": "lang_fr", "it": "lang_it"}
DOMAIN_NODE = {"cs": "concept_scientific_article_computer_science", "lit": "concept_literary_essay"}

ONTOLOGY = """// ===== Онтология предметной области «Автоматическое реферирование документов» =====
concept_document
<- sc_node_class;
=> nrel_main_idtf: [документ] (* <- lang_ru;; *);;

concept_scientific_article_computer_science
<- sc_node_class;
=> nrel_main_idtf: [научная статья по computer science] (* <- lang_ru;; *);
<= nrel_inclusion: concept_document;;

concept_literary_essay
<- sc_node_class;
=> nrel_main_idtf: [сочинение по литературе] (* <- lang_ru;; *);
<= nrel_inclusion: concept_document;;

concept_classic_summary
<- sc_node_class;
=> nrel_main_idtf: [классический реферат] (* <- lang_ru;; *);;

concept_keyword_summary
<- sc_node_class;
=> nrel_main_idtf: [реферат в виде списка ключевых слов] (* <- lang_ru;; *);;

concept_keyword
<- sc_node_class;
=> nrel_main_idtf: [ключевое слово] (* <- lang_ru;; *);;

concept_sentence
<- sc_node_class;
=> nrel_main_idtf: [предложение] (* <- lang_ru;; *);;

method_sentence_extraction
<- concept_summarization_method;
=> nrel_main_idtf: [метод sentence extraction] (* <- lang_ru;; *);;

nrel_summary
<- sc_node_norole_relation;
=> nrel_main_idtf: [реферат*] (* <- lang_ru;; *);;

nrel_keywords
<- sc_node_norole_relation;
=> nrel_main_idtf: [ключевые слова*] (* <- lang_ru;; *);;

nrel_subkeyword
<- sc_node_norole_relation;
=> nrel_main_idtf: [уточняющее ключевое словосочетание*] (* <- lang_ru;; *);;

nrel_text_language
<- sc_node_norole_relation;
=> nrel_main_idtf: [язык текста*] (* <- lang_ru;; *);;

nrel_source_document
<- sc_node_norole_relation;
=> nrel_main_idtf: [исходный документ*] (* <- lang_ru;; *);;

nrel_summarization_method
<- sc_node_norole_relation;
=> nrel_main_idtf: [метод реферирования*] (* <- lang_ru;; *);;

method_semantic_ostis
<- concept_summarization_method;
=> nrel_main_idtf: [семантический метод реферирования по базе знаний OSTIS] (* <- lang_ru;; *);;

concept_semantic_summary
<- sc_node_class;
=> nrel_main_idtf: [семантический реферат] (* <- lang_ru;; *);
<= nrel_inclusion: concept_classic_summary;;

concept_key_concept_summary
<- sc_node_class;
=> nrel_main_idtf: [реферат в виде ключевых понятий базы знаний] (* <- lang_ru;; *);
<= nrel_inclusion: concept_keyword_summary;;

nrel_key_concepts
<- sc_node_norole_relation;
=> nrel_main_idtf: [ключевые понятия*] (* <- lang_ru;; *);;

nrel_idtf
<- sc_node_norole_relation;
=> nrel_main_idtf: [идентификатор*] (* <- lang_ru;; *);;

nrel_inclusion
<- sc_node_norole_relation;
=> nrel_main_idtf: [включение*] (* <- lang_ru;; *);;

nrel_related
<- sc_node_norole_relation;
=> nrel_main_idtf: [ассоциативная связь*] (* <- lang_ru;; *);;

nrel_document_class
<- sc_node_norole_relation;
=> nrel_main_idtf: [класс документов предметной области*] (* <- lang_ru;; *);;

"""


def sys_idtf(text: str, prefix: str = "") -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).replace("œ", "oe").replace("æ", "ae")
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return (prefix + t)[:80] or prefix.rstrip("_")


def scs_string(text: str) -> str:
    return "[" + text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]") + "]"


def document_scs(doc_id: int, title: str, lang: str, domain: str, url: str,
                 sentences: list[str], keywords: list[dict]) -> str:
    d = f"document_{doc_id}"
    s_node, k_node = f"classic_summary_{doc_id}", f"keyword_summary_{doc_id}"
    lng = LANG_NODE.get(lang, "lang_" + lang)
    out = [f"// ===== Документ {doc_id}: {title} ====="]
    out.append(
        f"{d}\n<- concept_document;\n<- {DOMAIN_NODE.get(domain, 'concept_document')};\n"
        f"=> nrel_main_idtf: {scs_string(title)} (* <- {lng};; *);\n"
        f"=> nrel_text_language: {lng};\n"
        f"=> nrel_source_document: {scs_string(url)};\n"
        f"=> nrel_summary: {s_node};\n"
        f"=> nrel_keywords: {k_node};;\n")
    lines = [f"{s_node}\n<- concept_classic_summary;\n=> nrel_summarization_method: method_sentence_extraction;"]
    for i, sent in enumerate(sentences, 1):
        lines.append(f"-> rrel_{i}: ..sentence_{doc_id}_{i};")
    lines[-1] = lines[-1][:-1] + ";;"
    out.append("\n".join(lines) + "\n")
    for i, sent in enumerate(sentences, 1):
        out.append(f"..sentence_{doc_id}_{i}\n<- concept_sentence;\n=> nrel_main_idtf: {scs_string(sent)} "
                   f"(* <- {lng};; *);;\n")
    lines = [f"{k_node}\n<- concept_keyword_summary;"]
    for i, kw in enumerate(keywords, 1):
        lines.append(f"-> rrel_{i}: {sys_idtf(kw['term'], f'kw_{lang}_')};  // w(t,D) = {kw['weight']:.4f}")
    if len(lines) > 1:
        last, _, comment = lines[-1].partition("  //")
        lines[-1] = last[:-1] + ";;" + ("  //" + comment if comment else "")
    else:
        lines[-1] = lines[-1][:-1] + ";;"
    out.append("\n".join(lines) + "\n")
    for kw in keywords:
        node = sys_idtf(kw["term"], f"kw_{lang}_")
        block = [f"{node}\n<- concept_keyword;\n=> nrel_main_idtf: {scs_string(kw['term'])} (* <- {lng};; *);"]
        for ch in kw.get("children", []):
            block.append(f"=> nrel_subkeyword: {sys_idtf(ch['phrase'], f'kw_{lang}_')};")
        block[-1] = block[-1][:-1] + ";;"
        out.append("\n".join(block) + "\n")
        for ch in kw.get("children", []):
            out.append(f"{sys_idtf(ch['phrase'], f'kw_{lang}_')}\n<- concept_keyword;\n"
                       f"=> nrel_main_idtf: {scs_string(ch['phrase'])} (* <- {lng};; *);;\n")
    return "\n".join(out)


def semantic_scs(doc_id: int, lang: str, sentences: list[str], concepts: list[dict]) -> str:
    d = f"document_{doc_id}"
    s_node, k_node = f"semantic_summary_{doc_id}", f"key_concepts_{doc_id}"
    lng = LANG_NODE.get(lang, "lang_" + lang)
    out = [f"// ----- Документ {doc_id}: результат семантического метода (агент OSTIS) -----",
           f"{d}\n=> nrel_summary: {s_node};\n=> nrel_key_concepts: {k_node};;\n"]
    lines = [f"{s_node}\n<- concept_semantic_summary;\n=> nrel_summarization_method: method_semantic_ostis;"]
    for i, _ in enumerate(sentences, 1):
        lines.append(f"-> rrel_{i}: ..sem_sentence_{doc_id}_{i};")
    lines[-1] = lines[-1][:-1] + ";;"
    out.append("\n".join(lines) + "\n")
    for i, sent in enumerate(sentences, 1):
        out.append(f"..sem_sentence_{doc_id}_{i}\n<- concept_sentence;\n=> nrel_main_idtf: {scs_string(sent)} "
                   f"(* <- {lng};; *);;\n")
    flat = []
    for c in concepts:
        flat.append((c["concept"], c["weight"]))
        flat += [(ch["concept"], ch["weight"]) for ch in c.get("children", [])]
    lines = [f"{k_node}\n<- concept_key_concept_summary;"]
    for i, (cid, w) in enumerate(flat, 1):
        lines.append(f"-> rrel_{i}: {cid};  // a(c) = {w:.4f}")
    last, _, comment = lines[-1].partition("  //")
    lines[-1] = last[:-1] + ";;" + ("  //" + comment if comment else "")
    out.append("\n".join(lines) + "\n")
    return "\n".join(out)


def knowledge_base(fragments: list[str]) -> str:
    return ONTOLOGY + "\n" + "\n".join(fragments)


def document_graph(doc_id: int, title: str, lang: str, domain: str,
                   sentences: list[str], keywords: list[dict], method: str = "extraction") -> dict:
    nodes, edges = [], []

    def node(nid, label, kind):
        nodes.append({"id": nid, "label": label, "kind": kind})
        return nid

    d = node(f"document_{doc_id}", title, "doc")
    node("concept_document", "документ", "class")
    node(DOMAIN_NODE[domain], "научная статья (CS)" if domain == "cs" else "сочинение по литературе", "class")
    node(LANG_NODE[lang], "французский язык" if lang == "fr" else "итальянский язык", "class")
    edges += [{"from": "concept_document", "to": d, "kind": "member"},
              {"from": DOMAIN_NODE[domain], "to": d, "kind": "member"},
              {"from": d, "to": LANG_NODE[lang], "kind": "nrel", "rel": "язык текста*"}]
    sem = method == "ostis"
    s = node(f"{'semantic' if sem else 'classic'}_summary_{doc_id}",
             "семантический реферат" if sem else "классический реферат", "struct")
    k = node(f"{'key_concepts' if sem else 'keyword_summary'}_{doc_id}",
             "ключевые понятия" if sem else "ключевые слова", "struct")
    edges += [{"from": d, "to": s, "kind": "nrel", "rel": "реферат*"},
              {"from": d, "to": k, "kind": "nrel", "rel": "ключевые понятия*" if sem else "ключевые слова*"}]
    for i, sent in enumerate(sentences, 1):
        n = node(f"sentence_{doc_id}_{i}", sent[:48] + ("…" if len(sent) > 48 else ""), "link")
        edges.append({"from": s, "to": n, "kind": "rrel", "rel": f"{i}'"})
    for i, kw in enumerate(keywords, 1):
        n = node(kw.get("concept") or sys_idtf(kw["term"], f"kw_{lang}_"), kw["term"], "term")
        edges.append({"from": k, "to": n, "kind": "rrel", "rel": f"{i}'"})
        for ch in kw.get("children", []):
            c = ch.get("concept") or sys_idtf(ch["phrase"], f"kw_{lang}_")
            if not any(x["id"] == c for x in nodes):
                node(c, ch["phrase"], "subterm")
            edges.append({"from": n, "to": c, "kind": "nrel", "rel": "включение*" if sem else "уточн.*"})
    return {"nodes": nodes, "edges": edges}
