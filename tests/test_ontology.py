def test_loads_expected_types(ontology):
    assert "Person" in ontology.node_type_names()
    assert "Organization" in ontology.node_type_names()
    assert ontology.is_valid_node_type("Technology")
    assert not ontology.is_valid_node_type("Unicorn")


def test_relation_direction_enforced(ontology):
    # worksFor: Person -> Organization
    assert ontology.is_valid_relation("worksFor", "Person", "Organization")
    assert not ontology.is_valid_relation("worksFor", "Organization", "Person")
    assert not ontology.is_valid_relation("worksFor", "Person", "Person")


def test_unknown_relation_invalid(ontology):
    assert not ontology.is_valid_relation("befriends", "Person", "Person")


def test_schema_iri_present(ontology):
    assert ontology.schema_for("Person") == "https://schema.org/Person"
