"""Ontologie laden und pruefen."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import ONTOLOGY_PATH


@dataclass(frozen=True)
class Relation:
    name: str
    source_type: str
    target_type: str


@dataclass
class Ontology:
    node_types: dict          # typ -> {schema, properties}
    relations: dict           # name -> Relation

    def node_type_names(self) -> list[str]:
        return sorted(self.node_types)

    def relation_names(self) -> list[str]:
        return sorted(self.relations)

    def is_valid_node_type(self, t: str) -> bool:
        return t in self.node_types

    def is_valid_relation(self, name: str, source_type: str,
                          target_type: str) -> bool:
        rel = self.relations.get(name)
        if rel is None:
            return False
        return rel.source_type == source_type and rel.target_type == target_type

    def schema_for(self, node_type: str) -> str | None:
        nt = self.node_types.get(node_type)
        return nt.get("schema") if nt else None


def load_ontology(path: Path | None = None) -> Ontology:
    path = path or ONTOLOGY_PATH
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    node_types = raw.get("node_types", {}) or {}
    relations = {}
    for name, spec in (raw.get("relation_types", {}) or {}).items():
        relations[name] = Relation(
            name=name,
            source_type=spec["from"],
            target_type=spec["to"],
        )
    return Ontology(node_types=node_types, relations=relations)
