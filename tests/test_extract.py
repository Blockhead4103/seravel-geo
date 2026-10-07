import json

from geo.extract import build_extraction_prompt, extract_graph


def test_prompt_lists_allowed_types_and_relations(ontology):
    prompt = build_extraction_prompt("irgendein Inhalt", ontology)
    assert "Person" in prompt
    assert "worksFor" in prompt
    assert "irgendein Inhalt" in prompt


def _fake_completer(payload: dict):
    def _c(_prompt: str) -> str:
        return "```json\n" + json.dumps(payload) + "\n```"
    return _c


def test_extract_builds_valid_graph(ontology):
    payload = {
        "nodes": [
            {"id": "kevin-lancashire", "type": "Person", "name": "Kevin Lancashire"},
            {"id": "lancashire-digital", "type": "Organization",
             "name": "Lancashire Digital"},
        ],
        "edges": [
            {"source": "kevin-lancashire", "relation": "worksFor",
             "target": "lancashire-digital"},
        ],
    }
    result = extract_graph("...", ontology, _fake_completer(payload))
    assert result.graph.g.number_of_nodes() == 2
    assert result.graph.g.has_edge("kevin-lancashire", "lancashire-digital",
                                   key="worksFor")
    assert result.warnings == []


def test_extract_drops_invalid_type(ontology):
    payload = {
        "nodes": [
            {"id": "x", "type": "Dragon", "name": "X"},
            {"id": "kevin", "type": "Person", "name": "Kevin"},
        ],
        "edges": [],
    }
    result = extract_graph("...", ontology, _fake_completer(payload))
    assert result.graph.g.number_of_nodes() == 1
    assert any("Dragon" in w for w in result.warnings)


def test_extract_drops_invalid_relation(ontology):
    payload = {
        "nodes": [
            {"id": "kevin", "type": "Person", "name": "Kevin"},
            {"id": "ld", "type": "Organization", "name": "LD"},
        ],
        # servesIndustry ist Organization->Industry, nicht Person->Organization
        "edges": [{"source": "kevin", "relation": "servesIndustry", "target": "ld"}],
    }
    result = extract_graph("...", ontology, _fake_completer(payload))
    assert result.graph.g.number_of_edges() == 0
    assert any("nicht erlaubt" in w for w in result.warnings)


def test_extract_drops_edge_with_unknown_node(ontology):
    payload = {
        "nodes": [{"id": "kevin", "type": "Person", "name": "Kevin"}],
        "edges": [{"source": "kevin", "relation": "worksFor", "target": "ghost"}],
    }
    result = extract_graph("...", ontology, _fake_completer(payload))
    assert result.graph.g.number_of_edges() == 0
    assert any("unbekannter Knoten" in w for w in result.warnings)


def test_extract_node_without_name_dropped(ontology):
    payload = {"nodes": [{"id": "x", "type": "Person"}], "edges": []}
    result = extract_graph("...", ontology, _fake_completer(payload))
    assert result.graph.g.number_of_nodes() == 0
    assert any("ohne Namen" in w for w in result.warnings)
