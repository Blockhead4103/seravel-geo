"""Knowledge-Graph: JSON-LD <-> NetworkX, Validierung, Fakten, DOT.

Interne Darstellung: ``networkx.MultiDiGraph``.
  - Knoten: id -> Attribute {"type": <Ontologie-Typ>, "props": {name, ...}}
  - Kanten: (quelle, ziel, key=relation) -> {"relation": <Name>}

Persistenz: echtes JSON-LD mit @graph. Knotentypen und -eigenschaften folgen
schema.org (ueber @vocab); die Kanten-/Beziehungsbegriffe sind Begriffe der
Projekt-Ontologie unter einem eigenen Namensraum (geo:).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import networkx as nx

from .config import GRAPH_PATH
from .ontology import Ontology

GEO_NS = "https://seravel-geo.local/ontology#"

# Lesbare Satzvorlagen je Beziehung, fuer Fakten und llms.txt.
# {s} = Name der Quelle, {t} = Name des Ziels.
RELATION_PHRASES = {
    "worksFor": "{s} works for {t}.",
    "founderOf": "{s} is a founder of {t}.",
    "offers": "{s} offers the service {t}.",
    "hasExpertiseIn": "{s} has expertise in {t}.",
    "specializesIn": "{s} specializes in {t}.",
    "servesIndustry": "{s} serves the {t} industry.",
    "deliveredProject": "{s} delivered the project {t}.",
    "usesTechnology": "{s} uses the technology {t}.",
    "holdsCredential": "{s} holds the credential {t}.",
}


def slugify(text: str) -> str:
    """Erzeugt eine stabile, URL-taugliche Id aus einem Namen."""
    norm = unicodedata.normalize("NFKD", text)
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
    return norm or "node"


class KnowledgeGraph:
    def __init__(self) -> None:
        self.g: nx.MultiDiGraph = nx.MultiDiGraph()

    # -- Aufbau -----------------------------------------------------------
    def add_node(self, node_id: str, node_type: str, props: dict | None = None) -> str:
        props = dict(props or {})
        if self.g.has_node(node_id):
            existing = self.g.nodes[node_id]
            existing.setdefault("props", {})
            # Nur leere Felder auffuellen, vorhandene nicht ueberschreiben.
            for k, v in props.items():
                if v and not existing["props"].get(k):
                    existing["props"][k] = v
            if node_type and not existing.get("type"):
                existing["type"] = node_type
        else:
            self.g.add_node(node_id, type=node_type, props=props)
        return node_id

    def add_edge(self, source: str, target: str, relation: str) -> None:
        # key=relation verhindert Duplikate derselben Beziehung.
        if not self.g.has_edge(source, target, key=relation):
            self.g.add_edge(source, target, key=relation, relation=relation)

    def name_of(self, node_id: str) -> str:
        if not self.g.has_node(node_id):
            return node_id
        return self.g.nodes[node_id].get("props", {}).get("name", node_id)

    def type_of(self, node_id: str) -> str | None:
        if not self.g.has_node(node_id):
            return None
        return self.g.nodes[node_id].get("type")

    # -- Zusammenfuehren --------------------------------------------------
    def merge(self, other: "KnowledgeGraph") -> None:
        for nid, attrs in other.g.nodes(data=True):
            self.add_node(nid, attrs.get("type", ""), attrs.get("props", {}))
        for u, v, key in other.g.edges(keys=True):
            self.add_edge(u, v, key)

    # -- Validierung ------------------------------------------------------
    def validate(self, ontology: Ontology) -> list[str]:
        issues: list[str] = []
        for nid, attrs in self.g.nodes(data=True):
            nt = attrs.get("type")
            if not ontology.is_valid_node_type(nt):
                issues.append(f"Knoten '{nid}': unbekannter Typ '{nt}'.")
            if not attrs.get("props", {}).get("name"):
                issues.append(f"Knoten '{nid}': ohne Eigenschaft 'name'.")
        for u, v, key in self.g.edges(keys=True):
            st = self.g.nodes[u].get("type") if self.g.has_node(u) else None
            tt = self.g.nodes[v].get("type") if self.g.has_node(v) else None
            if not ontology.is_valid_relation(key, st, tt):
                issues.append(
                    f"Kante {u} --{key}--> {v}: nicht erlaubt fuer "
                    f"({st} -> {tt})."
                )
        return issues

    # -- Fakten -----------------------------------------------------------
    def facts(self) -> list[str]:
        """Menschlich lesbare, bestaetigbare Faktensaetze aus dem Graphen."""
        out: list[str] = []
        for nid, attrs in self.g.nodes(data=True):
            props = attrs.get("props", {})
            name = props.get("name", nid)
            desc = props.get("description")
            if desc:
                out.append(f"{name}: {desc}")
        for u, v, key in self.g.edges(keys=True):
            phrase = RELATION_PHRASES.get(key)
            if phrase:
                out.append(phrase.format(s=self.name_of(u), t=self.name_of(v)))
            else:
                out.append(f"{self.name_of(u)} {key} {self.name_of(v)}.")
        return out

    def stats(self) -> dict:
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "node_types": _count_by(
                attrs.get("type", "?") for _, attrs in self.g.nodes(data=True)
            ),
            "relations": _count_by(
                key for _, _, key in self.g.edges(keys=True)
            ),
        }

    # -- Export -----------------------------------------------------------
    def to_jsonld(self, ontology: Ontology) -> dict:
        context = _build_context(ontology)
        graph_items = []
        for nid, attrs in self.g.nodes(data=True):
            item = {"@id": nid, "@type": attrs.get("type")}
            item.update(attrs.get("props", {}))
            # ausgehende Kanten als Beziehungs-Eigenschaften
            rel_map: dict[str, list] = {}
            for _, v, key in self.g.out_edges(nid, keys=True):
                rel_map.setdefault(key, []).append({"@id": v})
            for rel, refs in rel_map.items():
                item[rel] = refs[0] if len(refs) == 1 else refs
            graph_items.append(item)
        graph_items.sort(key=lambda it: it["@id"])
        return {"@context": context, "@graph": graph_items}

    def to_dot(self) -> str:
        """Graphviz-DOT fuer st.graphviz_chart."""
        lines = ["digraph G {", '  rankdir=LR;',
                 '  node [shape=box, style="rounded,filled", '
                 'fillcolor="#eef3f8", fontname="Helvetica"];',
                 '  edge [fontname="Helvetica", fontsize=10, color="#64748b"];']
        for nid, attrs in self.g.nodes(data=True):
            label = f'{self.name_of(nid)}\\n({attrs.get("type", "?")})'
            lines.append(f'  "{nid}" [label="{_dot_escape(label)}"];')
        for u, v, key in self.g.edges(keys=True):
            lines.append(f'  "{u}" -> "{v}" [label="{_dot_escape(key)}"];')
        lines.append("}")
        return "\n".join(lines)

    # -- Import -----------------------------------------------------------
    @classmethod
    def from_jsonld(cls, doc: dict) -> "KnowledgeGraph":
        kg = cls()
        items = doc.get("@graph", [])
        reserved = {"@id", "@type", "@context"}
        relation_names = set(RELATION_PHRASES)
        # erst Knoten, dann Kanten
        for item in items:
            nid = item["@id"]
            node_type = item.get("@type")
            props = {}
            for k, val in item.items():
                if k in reserved or k in relation_names:
                    continue
                props[k] = val
            kg.add_node(nid, node_type, props)
        for item in items:
            nid = item["@id"]
            for rel in relation_names:
                if rel not in item:
                    continue
                refs = item[rel]
                if isinstance(refs, dict):
                    refs = [refs]
                for ref in refs:
                    target = ref.get("@id") if isinstance(ref, dict) else ref
                    if target is not None:
                        kg.add_edge(nid, target, rel)
        return kg

    # -- Datei ------------------------------------------------------------
    def save(self, ontology: Ontology, path: Path | None = None) -> Path:
        path = Path(path or GRAPH_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_jsonld(ontology), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "KnowledgeGraph":
        path = Path(path or GRAPH_PATH)
        if not path.exists():
            return cls()
        doc = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_jsonld(doc)


def _build_context(ontology: Ontology) -> dict:
    context: dict = {
        "@vocab": "https://schema.org/",
        "geo": GEO_NS,
    }
    for node_type in ontology.node_type_names():
        schema_iri = ontology.schema_for(node_type)
        if schema_iri:
            context[node_type] = schema_iri
    for rel in ontology.relation_names():
        context[rel] = {"@id": "geo:" + rel, "@type": "@id"}
    return context


def _count_by(values) -> dict:
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items()))


def _dot_escape(text: str) -> str:
    return text.replace('"', '\\"')
