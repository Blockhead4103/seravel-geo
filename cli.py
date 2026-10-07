#!/usr/bin/env python3
"""Kommandozeile fuer seravel-geo (lokal und in GitHub Actions).

Beispiele:
  python cli.py validate
  python cli.py facts
  python cli.py llmstxt            # llms.txt aus dem Graphen neu erzeugen
  python cli.py extract --url https://lancashire-digital.ch --merge
  python cli.py audit              # Audit mit konfigurierten Engines
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from geo import audit as audit_mod
from geo.config import GRAPH_PATH, LLMS_TXT_PATH, load_settings
from geo.extract import extract_graph, fetch_page_text
from geo.graph import KnowledgeGraph
from geo.llm import anthropic_complete, anthropic_engine, gemini_engine
from geo.llmstxt import generate_llms_txt
from geo.ontology import load_ontology
from geo.store import load_probes, save_audit


def _load_graph() -> KnowledgeGraph:
    return KnowledgeGraph.load(GRAPH_PATH)


def cmd_validate(args) -> int:
    kg = _load_graph()
    issues = kg.validate(load_ontology())
    if not issues:
        print("OK: Graph ist gueltig.")
        print(json.dumps(kg.stats(), ensure_ascii=False, indent=2))
        return 0
    print("Probleme gefunden:")
    for i in issues:
        print(f"  - {i}")
    return 1


def cmd_facts(args) -> int:
    for f in _load_graph().facts():
        print(f)
    return 0


def cmd_stats(args) -> int:
    print(json.dumps(_load_graph().stats(), ensure_ascii=False, indent=2))
    return 0


def cmd_llmstxt(args) -> int:
    settings = load_settings()
    kg = _load_graph()
    text = generate_llms_txt(kg, settings.site_name, settings.site_base_url)
    out = Path(args.out or LLMS_TXT_PATH)
    out.write_text(text, encoding="utf-8")
    print(f"llms.txt geschrieben: {out} ({len(text)} Zeichen)")
    return 0


def cmd_extract(args) -> int:
    settings = load_settings()
    if not settings.has_anthropic:
        print("Fehler: ANTHROPIC_API_KEY fehlt (fuer die Extraktion noetig).",
              file=sys.stderr)
        return 2
    if args.url:
        content = fetch_page_text(args.url)
    elif args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    else:
        content = sys.stdin.read()
    if not content.strip():
        print("Fehler: kein Inhalt.", file=sys.stderr)
        return 2

    ontology = load_ontology()
    complete = lambda p: anthropic_complete(  # noqa: E731
        p, model=settings.anthropic_model, api_key=settings.anthropic_api_key)
    result = extract_graph(content, ontology, complete)
    print("Vorgeschlagener Graph:")
    print(json.dumps(result.graph.to_jsonld(ontology), ensure_ascii=False,
                      indent=2))
    if result.warnings:
        print("\nWarnungen:", file=sys.stderr)
        for w in result.warnings:
            print(f"  - {w}", file=sys.stderr)
    if args.merge:
        kg = _load_graph()
        kg.merge(result.graph)
        kg.save(ontology, GRAPH_PATH)
        print(f"\nIn {GRAPH_PATH} zusammengefuehrt und gespeichert.")
    else:
        print("\nHinweis: ohne --merge nichts gespeichert (nur Vorschlag).")
    return 0


def cmd_audit(args) -> int:
    settings = load_settings()
    if not settings.has_anthropic:
        print("Fehler: ANTHROPIC_API_KEY fehlt (fuer den Judge noetig).",
              file=sys.stderr)
        return 2

    engines = {}
    if settings.has_anthropic:
        engines["claude"] = anthropic_engine(
            settings.anthropic_model, api_key=settings.anthropic_api_key)
    if settings.has_gemini:
        engines["gemini"] = gemini_engine(
            settings.gemini_model, api_key=settings.gemini_api_key)
    if not engines:
        print("Fehler: keine Audit-Engine verfuegbar.", file=sys.stderr)
        return 2

    probes = load_probes()
    if not probes:
        print("Fehler: keine Proben in data/probes.yaml.", file=sys.stderr)
        return 2

    kg = _load_graph()
    judge = lambda p: anthropic_complete(  # noqa: E731
        p, model=settings.anthropic_model, api_key=settings.anthropic_api_key)
    run = audit_mod.run_audit(engines, probes, kg, judge,
                              max_calls=settings.max_calls_per_audit)
    run.site_name = settings.site_name
    path = save_audit(run)
    print(f"Audit gespeichert: {path}")
    print(json.dumps(run.summary, ensure_ascii=False, indent=2))
    if run.stopped_early:
        print("Hinweis: wegen Kostenbremse vorzeitig gestoppt.", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="seravel-geo CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="Graph gegen Ontologie pruefen")
    sub.add_parser("facts", help="Fakten ausgeben")
    sub.add_parser("stats", help="Kennzahlen ausgeben")

    sp = sub.add_parser("llmstxt", help="llms.txt neu erzeugen")
    sp.add_argument("--out", help="Zielpfad (Default: ./llms.txt)")

    sp = sub.add_parser("extract", help="Inhalt zu Graph extrahieren")
    sp.add_argument("--url", help="Seite laden")
    sp.add_argument("--file", help="Datei lesen")
    sp.add_argument("--merge", action="store_true",
                    help="Ergebnis in data/graph.jsonld zusammenfuehren")

    sub.add_parser("audit", help="GEO-Audit ausfuehren")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "validate": cmd_validate, "facts": cmd_facts, "stats": cmd_stats,
        "llmstxt": cmd_llmstxt, "extract": cmd_extract, "audit": cmd_audit,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
