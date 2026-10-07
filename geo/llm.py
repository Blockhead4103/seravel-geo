"""LLM-Adapter: Anthropic (Extraktion + Judge) und Gemini (Audit-Engine).

Abgekapselt, damit sich API-Details an genau einer Stelle aendern lassen.
Eine "Engine" ist schlicht ein Callable ``str -> str`` (Prompt -> Antworttext).
Tests koennen eine Fake-Engine einsetzen, ohne echte API-Schluessel.

Wichtig (ehrlich): Die externen SDK-Aufrufe unten sind nach bestem Wissen
korrekt, aber SDKs und Modell-IDs aendern sich. Vor dem Produktiveinsatz
bitte gegen die aktuelle Doku pruefen:
  - Anthropic: docs.anthropic.com (Messages API)
  - Gemini: ai.google.dev (google-generativeai)
"""
from __future__ import annotations

import json
import re
from typing import Callable, Protocol

Engine = Callable[[str], str]


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# JSON-Hilfen
# --------------------------------------------------------------------------
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_block(text: str):
    """Extrahiert JSON aus einer Modellantwort.

    Toleriert ```json ... ```-Bloecke und fuehrenden/folgenden Text.
    Wirft LLMError, wenn kein gueltiges JSON gefunden wird.
    """
    if text is None:
        raise LLMError("Leere Antwort (None).")
    candidate = text.strip()
    m = _JSON_FENCE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Versuch: ersten {...}- oder [...]-Block herausschneiden
        start = _first_json_start(candidate)
        if start is not None:
            sub = _balanced_slice(candidate, start)
            if sub is not None:
                try:
                    return json.loads(sub)
                except json.JSONDecodeError:
                    pass
    raise LLMError("Antwort enthaelt kein gueltiges JSON:\n" + text[:500])


def _first_json_start(s: str):
    for i, ch in enumerate(s):
        if ch in "{[":
            return i
    return None


def _balanced_slice(s: str, start: int):
    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


# --------------------------------------------------------------------------
# Anthropic (Claude)
# --------------------------------------------------------------------------
def anthropic_complete(prompt: str, model: str, max_tokens: int = 4096,
                       api_key: str | None = None) -> str:
    """Einzelner Claude-Aufruf, gibt den Text der Antwort zurueck.

    Nutzt das offizielle ``anthropic``-SDK. Kein ``budget_tokens`` (auf
    aktuellen Modellen entfernt); Thinking bleibt adaptiv per Default.
    """
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - Abhaengigkeit fehlt
        raise LLMError(
            "Paket 'anthropic' nicht installiert. pip install anthropic"
        ) from exc

    client = Anthropic(api_key=api_key) if api_key else Anthropic()
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001 - an Aufrufer weiterreichen
        raise LLMError(f"Anthropic-Aufruf fehlgeschlagen: {exc}") from exc

    parts = [getattr(b, "text", "") for b in msg.content
             if getattr(b, "type", None) == "text"]
    return "".join(parts)


def anthropic_engine(model: str, api_key: str | None = None,
                     max_tokens: int = 2048) -> Engine:
    """Baut eine Audit-Engine, die Fragen mit Claude beantwortet."""
    def _engine(prompt: str) -> str:
        return anthropic_complete(prompt, model=model, max_tokens=max_tokens,
                                  api_key=api_key)
    return _engine


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------
def gemini_engine(model: str, api_key: str, max_tokens: int = 2048) -> Engine:
    """Baut eine Audit-Engine, die Fragen mit Gemini beantwortet.

    Nutzt 'google-generativeai'. Diese API und die Modellnamen bitte gegen
    ai.google.dev pruefen, sie aendern sich haeufiger als bei Anthropic.
    """
    def _engine(prompt: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "Paket 'google-generativeai' nicht installiert. "
                "pip install google-generativeai"
            ) from exc
        try:
            genai.configure(api_key=api_key)
            gm = genai.GenerativeModel(model)
            resp = gm.generate_content(prompt)
            return getattr(resp, "text", "") or ""
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Gemini-Aufruf fehlgeschlagen: {exc}") from exc
    return _engine


class Completer(Protocol):
    def __call__(self, prompt: str) -> str: ...
