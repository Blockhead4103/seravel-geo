import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geo.graph import KnowledgeGraph  # noqa: E402
from geo.ontology import load_ontology  # noqa: E402


@pytest.fixture
def ontology():
    return load_ontology()


@pytest.fixture
def sample_graph():
    kg = KnowledgeGraph()
    kg.add_node("kevin-lancashire", "Person",
                {"name": "Kevin Lancashire", "jobTitle": "Consultant",
                 "description": "Digital consultant."})
    kg.add_node("lancashire-digital", "Organization",
                {"name": "Lancashire Digital",
                 "url": "https://lancashire-digital.ch"})
    kg.add_node("aem", "Technology", {"name": "Adobe Experience Manager"})
    kg.add_node("pharma", "Industry", {"name": "Pharmaceuticals"})
    kg.add_edge("kevin-lancashire", "lancashire-digital", "worksFor")
    kg.add_edge("kevin-lancashire", "aem", "hasExpertiseIn")
    kg.add_edge("lancashire-digital", "pharma", "servesIndustry")
    return kg
