from geo.llmstxt import generate_llms_txt


def test_structure(sample_graph):
    text = generate_llms_txt(sample_graph, "Lancashire Digital",
                             "https://lancashire-digital.ch")
    assert text.startswith("# Lancashire Digital")
    assert "> Digital consultant." in text          # Blockquote-Zusammenfassung
    assert "https://lancashire-digital.ch" in text
    assert "## About" in text
    assert "## Expertise & Technologies" in text
    assert "Adobe Experience Manager" in text
    assert "## Industries" in text
    assert "Pharmaceuticals" in text
    assert "## Verified facts" in text


def test_deterministic(sample_graph):
    a = generate_llms_txt(sample_graph, "X", "https://x")
    b = generate_llms_txt(sample_graph, "X", "https://x")
    assert a == b


def test_empty_graph():
    from geo.graph import KnowledgeGraph
    text = generate_llms_txt(KnowledgeGraph(), "Empty", "https://x")
    assert text.startswith("# Empty")
