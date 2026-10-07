from geo.graph import KnowledgeGraph, slugify


def test_slugify():
    assert slugify("Kevin Lancashire") == "kevin-lancashire"
    assert slugify("Adobe Experience Manager (AEM)") == "adobe-experience-manager-aem"
    assert slugify("Zürich") == "zurich"
    assert slugify("") == "node"


def test_jsonld_roundtrip(sample_graph, ontology):
    doc = sample_graph.to_jsonld(ontology)
    assert "@context" in doc and "@graph" in doc
    restored = KnowledgeGraph.from_jsonld(doc)
    assert restored.g.number_of_nodes() == sample_graph.g.number_of_nodes()
    assert restored.g.number_of_edges() == sample_graph.g.number_of_edges()
    # Kante erhalten?
    assert restored.g.has_edge("kevin-lancashire", "lancashire-digital",
                               key="worksFor")


def test_facts_contains_relation_sentences(sample_graph):
    facts = sample_graph.facts()
    assert "Kevin Lancashire works for Lancashire Digital." in facts
    assert "Kevin Lancashire has expertise in Adobe Experience Manager." in facts
    assert "Lancashire Digital serves the Pharmaceuticals industry." in facts


def test_validate_clean(sample_graph, ontology):
    assert sample_graph.validate(ontology) == []


def test_validate_flags_bad_type_and_relation(ontology):
    kg = KnowledgeGraph()
    kg.add_node("a", "Dragon", {"name": "A"})
    kg.add_node("b", "Person", {"name": "B"})
    kg.add_edge("a", "b", "worksFor")   # Dragon->Person nicht erlaubt
    issues = kg.validate(ontology)
    assert any("Dragon" in i for i in issues)
    assert any("nicht erlaubt" in i for i in issues)


def test_merge_is_additive(sample_graph, ontology):
    other = KnowledgeGraph()
    other.add_node("python", "Technology", {"name": "Python"})
    other.add_edge("kevin-lancashire", "python", "hasExpertiseIn")
    before = sample_graph.g.number_of_nodes()
    sample_graph.merge(other)
    assert sample_graph.g.number_of_nodes() == before + 1
    assert sample_graph.g.has_edge("kevin-lancashire", "python",
                                   key="hasExpertiseIn")


def test_merge_does_not_duplicate_edges(sample_graph):
    before_edges = sample_graph.g.number_of_edges()
    dup = KnowledgeGraph()
    dup.add_node("kevin-lancashire", "Person", {"name": "Kevin Lancashire"})
    dup.add_node("lancashire-digital", "Organization", {"name": "Lancashire Digital"})
    dup.add_edge("kevin-lancashire", "lancashire-digital", "worksFor")
    sample_graph.merge(dup)
    assert sample_graph.g.number_of_edges() == before_edges


def test_dot_contains_nodes(sample_graph):
    dot = sample_graph.to_dot()
    assert dot.startswith("digraph")
    assert "kevin-lancashire" in dot
    assert "worksFor" in dot


def test_stats(sample_graph):
    stats = sample_graph.stats()
    assert stats["nodes"] == 4
    assert stats["edges"] == 3
    assert stats["node_types"]["Person"] == 1


def test_save_and_load(tmp_path, sample_graph, ontology):
    path = tmp_path / "g.jsonld"
    sample_graph.save(ontology, path)
    loaded = KnowledgeGraph.load(path)
    assert loaded.g.number_of_nodes() == 4
    assert "Kevin Lancashire works for Lancashire Digital." in loaded.facts()


def test_load_missing_returns_empty(tmp_path):
    kg = KnowledgeGraph.load(tmp_path / "nope.jsonld")
    assert kg.g.number_of_nodes() == 0
