"""llms.txt aus dem Knowledge-Graph erzeugen.

llms.txt ist eine aufkommende, NICHT ratifizierte Konvention (Vorschlag von
Answer.AI, 2024): eine Markdown-Datei unter /llms.txt, die einer KI die
Website strukturiert zusammenfasst. Ob und wie KI-Crawler sie auswerten, ist
nicht garantiert. Wir erzeugen sie deterministisch aus bestaetigten Fakten.
"""
from __future__ import annotations

from .graph import KnowledgeGraph


def _targets(kg: KnowledgeGraph, relation: str) -> list[str]:
    names = []
    for _, v, key in kg.g.edges(keys=True):
        if key == relation:
            names.append(kg.name_of(v))
    return sorted(set(names))


def _nodes_of_type(kg: KnowledgeGraph, node_type: str) -> list[str]:
    ids = [nid for nid, a in kg.g.nodes(data=True) if a.get("type") == node_type]
    return sorted(ids, key=kg.name_of)


def _primary_person(kg: KnowledgeGraph) -> str | None:
    people = _nodes_of_type(kg, "Person")
    return people[0] if people else None


def generate_llms_txt(kg: KnowledgeGraph, site_name: str,
                      base_url: str) -> str:
    lines: list[str] = []
    lines.append(f"# {site_name}")
    lines.append("")

    # Zusammenfassung aus Beschreibung der Hauptperson oder Organisation
    summary = None
    person = _primary_person(kg)
    if person:
        summary = kg.g.nodes[person].get("props", {}).get("description")
    if not summary:
        orgs = _nodes_of_type(kg, "Organization")
        if orgs:
            summary = kg.g.nodes[orgs[0]].get("props", {}).get("description")
    if summary:
        lines.append(f"> {summary}")
        lines.append("")

    lines.append(f"Quelle: {base_url}")
    lines.append("")

    # Abschnitte
    sections: list[tuple[str, list[str]]] = []

    about: list[str] = []
    for nid in _nodes_of_type(kg, "Person") + _nodes_of_type(kg, "Organization"):
        p = kg.g.nodes[nid].get("props", {})
        name = p.get("name", nid)
        bits = []
        if p.get("jobTitle"):
            bits.append(p["jobTitle"])
        if p.get("description"):
            bits.append(p["description"])
        suffix = f" — {'; '.join(bits)}" if bits else ""
        about.append(f"- {name}{suffix}")
        for link in _as_list(p.get("sameAs")) + _as_list(p.get("url")):
            about.append(f"  - {link}")
    if about:
        sections.append(("About", about))

    expertise = sorted(set(_targets(kg, "hasExpertiseIn")
                           + _targets(kg, "specializesIn")))
    if expertise:
        sections.append(("Expertise & Technologies",
                         [f"- {name}" for name in expertise]))

    services = _targets(kg, "offers")
    if services:
        sections.append(("Services", [f"- {name}" for name in services]))

    industries = _targets(kg, "servesIndustry")
    if industries:
        sections.append(("Industries", [f"- {name}" for name in industries]))

    projects = _nodes_of_type(kg, "Project")
    if projects:
        rows = []
        for nid in projects:
            p = kg.g.nodes[nid].get("props", {})
            desc = f" — {p['description']}" if p.get("description") else ""
            rows.append(f"- {p.get('name', nid)}{desc}")
        sections.append(("Projects", rows))

    credentials = _nodes_of_type(kg, "Credential")
    if credentials:
        sections.append(("Credentials",
                         [f"- {kg.name_of(nid)}" for nid in credentials]))

    for title, rows in sections:
        lines.append(f"## {title}")
        lines.extend(rows)
        lines.append("")

    # Faktenliste als klarer, maschinenlesbarer Block
    facts = kg.facts()
    if facts:
        lines.append("## Verified facts")
        lines.extend(f"- {f}" for f in facts)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]
