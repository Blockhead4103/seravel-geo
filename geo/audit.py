"""GEO/AEO-Audit: KI-Antworten gegen bestaetigte Fakten messen.

Methodik angelehnt an Seravel: Jede KI-Antwort wird in Aussagen zerlegt und
gegen die bestaetigten Fakten geprueft. Pro Frage gibt es erwartete Fakten
(was eine richtige Antwort nennen sollte). Daraus:
  - Abdeckung  (coverage): erwartete Fakten, die genannt wurden
  - Luecken    (missing):  erwartete Fakten, die fehlen
  - Halluzinationen: Aussagen, die den Fakten widersprechen (contradicted)
    oder unbelegt sind (unsupported)

Der GEO-Score ist eine transparente, HANDGEWAEHLTE Formel (keine
wissenschaftliche Metrik). Gewichte stehen unten und lassen sich anpassen.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field
from typing import Callable

from .graph import KnowledgeGraph
from .llm import parse_json_block

Engine = Callable[[str], str]
Completer = Callable[[str], str]

# Gewichte des GEO-Scores (handgewaehlt, anpassbar):
PENALTY_CONTRADICTED = 15   # klar falsche Aussage
PENALTY_UNSUPPORTED = 6     # unbelegte Aussage


@dataclass
class Probe:
    id: str
    question: str
    expected: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    claims: list[dict]              # [{"text":..., "status":...}]
    covered_expected: list[str]
    missing_expected: list[str]

    @property
    def contradicted(self) -> int:
        return sum(1 for c in self.claims if c.get("status") == "contradicted")

    @property
    def unsupported(self) -> int:
        return sum(1 for c in self.claims if c.get("status") == "unsupported")

    @property
    def supported(self) -> int:
        return sum(1 for c in self.claims if c.get("status") == "supported")


@dataclass
class ProbeResult:
    probe_id: str
    engine: str
    question: str
    answer: str
    coverage_pct: float
    hallucinations: int
    missing: int
    geo_score: int
    verdict: dict


@dataclass
class AuditRun:
    created_at: str
    site_name: str
    results: list[dict]
    summary: dict
    calls_used: int
    stopped_early: bool = False


def build_judge_prompt(answer: str, confirmed_facts: list[str],
                       expected_facts: list[str]) -> str:
    facts_block = "\n".join(f"- {f}" for f in confirmed_facts) or "(keine)"
    expected_block = "\n".join(f"- {f}" for f in expected_facts) or "(keine)"
    return f"""Du bewertest die Antwort eines KI-Assistenten gegen bestaetigte Fakten.

BESTAETIGTE FAKTEN (einzige Wahrheit):
{facts_block}

ERWARTETE FAKTEN fuer diese Frage (sollten in einer guten Antwort vorkommen):
{expected_block}

KI-ANTWORT:
\"\"\"
{answer.strip()}
\"\"\"

Aufgabe:
1. Zerlege die KI-Antwort in einzelne Sachaussagen.
2. Ordne jeder Aussage genau einen Status zu:
   - "supported": durch die bestaetigten Fakten gedeckt
   - "contradicted": widerspricht einem bestaetigten Fakt
   - "unsupported": weder gedeckt noch widersprochen (unbelegt)
3. Welche der ERWARTETEN Fakten wurden genannt, welche fehlen?

Antworte NUR mit JSON in genau diesem Format:
{{
  "claims": [{{"text": "...", "status": "supported"}}],
  "covered_expected": ["exakter Text eines erwarteten Fakts, der vorkam"],
  "missing_expected": ["exakter Text eines erwarteten Fakts, der fehlt"]
}}
"""


def judge_answer(answer: str, confirmed_facts: list[str],
                 expected_facts: list[str], complete: Completer) -> Verdict:
    prompt = build_judge_prompt(answer, confirmed_facts, expected_facts)
    data = parse_json_block(complete(prompt))
    return Verdict(
        claims=list(data.get("claims", []) or []),
        covered_expected=list(data.get("covered_expected", []) or []),
        missing_expected=list(data.get("missing_expected", []) or []),
    )


def score_verdict(verdict: Verdict, expected_count: int) -> tuple[float, int, int, int]:
    """Gibt (coverage_pct, hallucinations, missing, geo_score) zurueck."""
    if expected_count > 0:
        coverage_pct = round(
            100.0 * len(verdict.covered_expected) / expected_count, 1
        )
    else:
        coverage_pct = 100.0
    hallucinations = verdict.contradicted + verdict.unsupported
    missing = len(verdict.missing_expected)
    penalty = (PENALTY_CONTRADICTED * verdict.contradicted
               + PENALTY_UNSUPPORTED * verdict.unsupported)
    geo_score = int(max(0, min(100, round(coverage_pct - penalty))))
    return coverage_pct, hallucinations, missing, geo_score


def run_probe(engine_name: str, engine: Engine, probe: Probe,
              confirmed_facts: list[str], judge_complete: Completer) -> ProbeResult:
    answer = engine(probe.question)
    verdict = judge_answer(answer, confirmed_facts, probe.expected, judge_complete)
    coverage, halluc, missing, score = score_verdict(verdict, len(probe.expected))
    return ProbeResult(
        probe_id=probe.id,
        engine=engine_name,
        question=probe.question,
        answer=answer,
        coverage_pct=coverage,
        hallucinations=halluc,
        missing=missing,
        geo_score=score,
        verdict=asdict(verdict),
    )


def run_audit(engines: dict[str, Engine], probes: list[Probe],
              kg: KnowledgeGraph, judge_complete: Completer,
              max_calls: int = 200) -> AuditRun:
    """Fuehrt alle Proben gegen alle Engines aus.

    Kostenbremse: je Probe x Engine fallen 2 Aufrufe an (Engine + Judge).
    Bei Erreichen von ``max_calls`` wird abgebrochen (stopped_early=True).
    """
    confirmed_facts = kg.facts()
    results: list[ProbeResult] = []
    calls = 0
    stopped = False
    for probe in probes:
        for engine_name, engine in engines.items():
            if calls + 2 > max_calls:
                stopped = True
                break
            results.append(
                run_probe(engine_name, engine, probe, confirmed_facts,
                          judge_complete)
            )
            calls += 2
        if stopped:
            break

    summary = _summarize(results)
    return AuditRun(
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        site_name="",
        results=[asdict(r) for r in results],
        summary=summary,
        calls_used=calls,
        stopped_early=stopped,
    )


def _summarize(results: list[ProbeResult]) -> dict:
    by_engine: dict[str, dict] = {}
    for r in results:
        agg = by_engine.setdefault(r.engine, {
            "probes": 0, "geo_score_sum": 0, "coverage_sum": 0.0,
            "hallucinations": 0, "missing": 0,
        })
        agg["probes"] += 1
        agg["geo_score_sum"] += r.geo_score
        agg["coverage_sum"] += r.coverage_pct
        agg["hallucinations"] += r.hallucinations
        agg["missing"] += r.missing
    out = {}
    for engine, agg in by_engine.items():
        n = max(1, agg["probes"])
        out[engine] = {
            "probes": agg["probes"],
            "avg_geo_score": round(agg["geo_score_sum"] / n, 1),
            "avg_coverage_pct": round(agg["coverage_sum"] / n, 1),
            "hallucinations": agg["hallucinations"],
            "missing": agg["missing"],
        }
    return out
