"""Aus Website-Inhalt pruefbare Entitaeten und Beziehungen gewinnen.

Claude liefert einen Vorschlag (Knoten + Kanten) streng nach Ontologie;
ungueltige Teile werden verworfen und als Warnung zurueckgegeben. Nichts
gilt automatisch als wahr: Der Mensch bestaetigt den Graphen (vgl. Seravel).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .graph import KnowledgeGraph, slugify
from .llm import parse_json_block
from .ontology import Ontology

Completer = Callable[[str], str]


@dataclass
class ExtractionResult:
    graph: KnowledgeGraph
    warnings: list[str] = field(default_factory=list)
    raw: str = ""


def build_extraction_prompt(content: str, ontology: Ontology) -> str:
    node_types = ", ".join(ontology.node_type_names())
    rel_lines = []
    for name in ontology.relation_names():
        rel = ontology.relations[name]
        rel_lines.append(f"  - {name}: ({rel.source_type}) -> ({rel.target_type})")
    rels = "\n".join(rel_lines)
    return f"""Du extrahierst einen Knowledge-Graph aus Website-Inhalt.

Erlaubte Knotentypen: {node_types}

Erlaubte Beziehungen (nur diese, Richtung beachten):
{rels}

Regeln:
- Verwende ausschliesslich die erlaubten Typen und Beziehungen.
- Erfinde nichts. Nur was im Text belegt ist.
- "id": kurzer Kleinbuchstaben-Slug (z. B. "kevin-lancashire").
- Jede Kante muss zu den Typen ihrer Knoten passen.
- Antworte NUR mit JSON in genau diesem Format, ohne weiteren Text:

{{
  "nodes": [
    {{"id": "kevin-lancashire", "type": "Person", "name": "Kevin Lancashire",
      "jobTitle": "...", "description": "...", "sameAs": ["https://..."]}}
  ],
  "edges": [
    {{"source": "kevin-lancashire", "relation": "worksFor", "target": "lancashire-digital"}}
  ]
}}

Website-Inhalt:
\"\"\"
{content.strip()}
\"\"\"
"""


def extract_graph(content: str, ontology: Ontology,
                  complete: Completer) -> ExtractionResult:
    """Extrahiert einen Graphen aus Inhalt. ``complete`` ist ein Callable
    str->str (Claude-Aufruf oder Fake im Test)."""
    prompt = build_extraction_prompt(content, ontology)
    raw = complete(prompt)
    data = parse_json_block(raw)
    return _result_from_data(data, ontology, raw)


def _result_from_data(data: dict, ontology: Ontology, raw: str) -> ExtractionResult:
    kg = KnowledgeGraph()
    warnings: list[str] = []

    reserved = {"id", "type"}
    valid_ids: set[str] = set()
    for node in data.get("nodes", []) or []:
        nid = node.get("id") or slugify(node.get("name", ""))
        ntype = node.get("type")
        if not ontology.is_valid_node_type(ntype):
            warnings.append(f"Knoten '{nid}' mit unbekanntem Typ '{ntype}' verworfen.")
            continue
        if not node.get("name"):
            warnings.append(f"Knoten '{nid}' ohne Namen verworfen.")
            continue
        props = {k: v for k, v in node.items() if k not in reserved}
        kg.add_node(nid, ntype, props)
        valid_ids.add(nid)

    for edge in data.get("edges", []) or []:
        src = edge.get("source")
        tgt = edge.get("target")
        rel = edge.get("relation")
        if src not in valid_ids or tgt not in valid_ids:
            warnings.append(
                f"Kante {src} --{rel}--> {tgt} verworfen (unbekannter Knoten)."
            )
            continue
        st = kg.type_of(src)
        tt = kg.type_of(tgt)
        if not ontology.is_valid_relation(rel, st, tt):
            warnings.append(
                f"Kante {src} --{rel}--> {tgt} verworfen "
                f"(nicht erlaubt fuer {st} -> {tt})."
            )
            continue
        kg.add_edge(src, tgt, rel)

    return ExtractionResult(graph=kg, warnings=warnings, raw=raw)


# --------------------------------------------------------------------------
# Website-Inhalt holen (nicht live getestet; robots.txt bitte beachten)
# --------------------------------------------------------------------------
def fetch_page_text(url: str, timeout: int = 20) -> str:
    """Laedt eine Seite und gibt sichtbaren Text zurueck.

    Hinweis: in der Entwicklungsumgebung ohne Internet nicht live getestet.
    """
    import requests  # lokaler Import, optionale Abhaengigkeit
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "seravel-geo/0.1 (+https://lancashire-digital.ch)"}
    resp = requests.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
