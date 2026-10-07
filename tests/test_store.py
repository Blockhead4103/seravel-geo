from geo.audit import AuditRun, Probe
from geo.store import (
    audit_history,
    list_audits,
    load_probes,
    save_audit,
    save_probes,
)


def test_probes_roundtrip(tmp_path):
    path = tmp_path / "probes.yaml"
    probes = [
        Probe(id="a", question="Q1?", expected=["f1", "f2"]),
        Probe(id="b", question="Q2?", expected=[]),
    ]
    save_probes(probes, path)
    loaded = load_probes(path)
    assert [p.id for p in loaded] == ["a", "b"]
    assert loaded[0].expected == ["f1", "f2"]


def test_load_probes_missing(tmp_path):
    assert load_probes(tmp_path / "nope.yaml") == []


def test_audit_save_and_history(tmp_path):
    run = AuditRun(
        created_at="2026-01-01T00:00:00+00:00",
        site_name="Test",
        results=[],
        summary={"claude": {"avg_geo_score": 80.0, "probes": 1,
                            "avg_coverage_pct": 90.0, "hallucinations": 0,
                            "missing": 0}},
        calls_used=2,
    )
    save_audit(run, tmp_path)
    assert len(list_audits(tmp_path)) == 1
    hist = audit_history(tmp_path)
    assert hist[0]["summary"]["claude"]["avg_geo_score"] == 80.0
