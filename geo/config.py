"""Konfiguration aus Umgebungsvariablen und .env.

Nichts hier erfindet Werte. Fehlt ein Schluessel, wird die betroffene
Funktion klar fehlschlagen, statt still weiterzulaufen.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Projektwurzel = Ordner ueber diesem Modul
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GRAPH_PATH = DATA_DIR / "graph.jsonld"
PROBES_PATH = DATA_DIR / "probes.yaml"
ONTOLOGY_PATH = ROOT / "ontology.yaml"
AUDITS_DIR = DATA_DIR / "audits"
LLMS_TXT_PATH = ROOT / "llms.txt"


def _load_dotenv() -> None:
    """Minimaler .env-Loader (ohne externe Abhaengigkeit).

    Setzt nur Schluessel, die noch nicht in der Umgebung stehen, damit
    echte Umgebungsvariablen (z. B. in GitHub Actions) Vorrang haben.
    """
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    # Anthropic (Extraktion + Bewertung/Judge)
    anthropic_api_key: str | None
    anthropic_model: str
    # Gemini (optional, nur fuer Audit-Engine)
    gemini_api_key: str | None
    gemini_model: str
    # Website
    site_base_url: str
    site_name: str
    # Kostenbremse: max. API-Aufrufe je Audit-Lauf
    max_calls_per_audit: int

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        # Default laut claude-api-Skill: claude-opus-5-5. Per Env aenderbar.
        # Guenstiger (und meist ausreichend fuer Extraktion): claude-sonnet-5-5
        # oder claude-haiku-5-5. Modell-IDs bitte gegen die aktuelle
        # Anthropic-Doku pruefen, da sie sich aendern.
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        # Modellname bitte gegen ai.google.dev pruefen; aendert sich.
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-1.5-pro"),
        site_base_url=os.environ.get("SITE_BASE_URL", "https://lancashire-digital.ch"),
        site_name=os.environ.get("SITE_NAME", "Lancashire Digital"),
        max_calls_per_audit=int(os.environ.get("MAX_CALLS_PER_AUDIT", "200")),
    )
