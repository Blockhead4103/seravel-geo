import json

from geo.audit import (
    Probe,
    Verdict,
    judge_answer,
    run_audit,
    score_verdict,
)


def test_score_verdict_math():
    verdict = Verdict(
        claims=[
            {"text": "a", "status": "supported"},
            {"text": "b", "status": "supported"},
            {"text": "c", "status": "contradicted"},
        ],
        covered_expected=["fact a"],
        missing_expected=["fact b"],
    )
    coverage, halluc, missing, score = score_verdict(verdict, expected_count=2)
    assert coverage == 50.0
    assert halluc == 1
    assert missing == 1
    # 50 - 15*1 (contradicted) = 35
    assert score == 35


def test_score_verdict_no_expected_is_full_coverage():
    verdict = Verdict(claims=[], covered_expected=[], missing_expected=[])
    coverage, halluc, missing, score = score_verdict(verdict, expected_count=0)
    assert coverage == 100.0
    assert score == 100


def _judge_returning(payload: dict):
    def _j(_prompt: str) -> str:
        return json.dumps(payload)
    return _j


def test_judge_answer_parses(monkeypatch):
    payload = {
        "claims": [{"text": "Kevin works for LD", "status": "supported"}],
        "covered_expected": ["Kevin Lancashire works for Lancashire Digital."],
        "missing_expected": [],
    }
    verdict = judge_answer("some answer", ["fact"], ["expected"],
                           _judge_returning(payload))
    assert verdict.supported == 1
    assert verdict.covered_expected == [
        "Kevin Lancashire works for Lancashire Digital."]


def test_run_audit_happy_path(sample_graph):
    probes = [
        Probe(id="p1", question="Q1?",
              expected=["Kevin Lancashire works for Lancashire Digital."]),
        Probe(id="p2", question="Q2?", expected=[]),
    ]
    engines = {"claude": lambda q: "Kevin Lancashire works for Lancashire Digital."}
    judge = _judge_returning({
        "claims": [{"text": "x", "status": "supported"}],
        "covered_expected": ["Kevin Lancashire works for Lancashire Digital."],
        "missing_expected": [],
    })
    run = run_audit(engines, probes, sample_graph, judge, max_calls=100)
    assert len(run.results) == 2
    assert run.calls_used == 4
    assert not run.stopped_early
    assert "claude" in run.summary
    assert run.summary["claude"]["probes"] == 2


def test_run_audit_cost_guard_stops_early(sample_graph):
    probes = [Probe(id=f"p{i}", question="Q?", expected=[]) for i in range(5)]
    engines = {"claude": lambda q: "answer"}
    judge = _judge_returning({"claims": [], "covered_expected": [],
                              "missing_expected": []})
    run = run_audit(engines, probes, sample_graph, judge, max_calls=2)
    assert run.stopped_early
    assert len(run.results) == 1   # nur eine Probe passte in 2 Aufrufe
    assert run.calls_used == 2


def test_run_audit_two_engines(sample_graph):
    probes = [Probe(id="p1", question="Q?", expected=[])]
    engines = {
        "claude": lambda q: "answer A",
        "gemini": lambda q: "answer B",
    }
    judge = _judge_returning({"claims": [{"text": "x", "status": "unsupported"}],
                              "covered_expected": [], "missing_expected": []})
    run = run_audit(engines, probes, sample_graph, judge, max_calls=100)
    assert set(run.summary) == {"claude", "gemini"}
    # unsupported zaehlt als Halluzination
    assert run.summary["claude"]["hallucinations"] == 1
