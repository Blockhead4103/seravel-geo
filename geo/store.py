"""Dateibasierte Persistenz: Proben laden, Audit-Laeufe speichern/lesen."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import yaml

from .audit import AuditRun, Probe
from .config import AUDITS_DIR, PROBES_PATH


def load_probes(path: Path | None = None) -> list[Probe]:
    path = Path(path or PROBES_PATH)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    probes = []
    for item in raw.get("probes", []) or []:
        probes.append(Probe(
            id=item["id"],
            question=item["question"],
            expected=list(item.get("expected", []) or []),
        ))
    return probes


def save_probes(probes: list[Probe], path: Path | None = None) -> Path:
    path = Path(path or PROBES_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"probes": [asdict(p) for p in probes]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


def save_audit(run: AuditRun, audits_dir: Path | None = None) -> Path:
    audits_dir = Path(audits_dir or AUDITS_DIR)
    audits_dir.mkdir(parents=True, exist_ok=True)
    # Dateiname aus Zeitstempel, dateisystemtauglich
    stamp = run.created_at.replace(":", "").replace("-", "").replace("+", "p")
    path = audits_dir / f"audit_{stamp}.json"
    path.write_text(json.dumps(asdict(run), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def list_audits(audits_dir: Path | None = None) -> list[Path]:
    audits_dir = Path(audits_dir or AUDITS_DIR)
    if not audits_dir.exists():
        return []
    return sorted(audits_dir.glob("audit_*.json"))


def load_audit(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def audit_history(audits_dir: Path | None = None) -> list[dict]:
    """Chronologische Liste {created_at, summary} ueber alle Laeufe."""
    history = []
    for p in list_audits(audits_dir):
        data = load_audit(p)
        history.append({
            "created_at": data.get("created_at"),
            "summary": data.get("summary", {}),
            "path": str(p),
        })
    return history
