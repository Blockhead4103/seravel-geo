"""seravel-geo: internes Dashboard (Streamlit).

Vier Reiter: Graph & Fakten, Extraktion, llms.txt, Audit.
Einzelmandant, interne Nutzung fuer eine Website.
"""
from __future__ import annotations

import json
import os

import streamlit as st

from geo import audit as audit_mod
from geo.config import GRAPH_PATH, LLMS_TXT_PATH, load_settings
from geo.extract import extract_graph, fetch_page_text
from geo.graph import KnowledgeGraph
from geo.llm import LLMError, anthropic_complete, anthropic_engine, gemini_engine
from geo.llmstxt import generate_llms_txt
from geo.ontology import load_ontology
from geo.store import audit_history, load_probes, save_audit

st.set_page_config(page_title="seravel-geo", page_icon="🔎", layout="wide")


def _secret(name: str) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - keine secrets.toml vorhanden
        pass
    return os.environ.get(name)


def _password_gate() -> bool:
    expected = _secret("APP_PASSWORD")
    if not expected:
        # Kein Passwort gesetzt: lokal offen. Fuer Online-Deploy dringend setzen.
        return True
    if st.session_state.get("authed"):
        return True
    st.title("🔎 seravel-geo")
    pw = st.text_input("Passwort", type="password")
    if st.button("Anmelden"):
        if pw == expected:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Falsches Passwort.")
    st.caption("Kein APP_PASSWORD gesetzt = offener Zugang. Fuer Online-Betrieb setzen.")
    return False


@st.cache_data(show_spinner=False)
def _ontology():
    return load_ontology()


def _load_graph() -> KnowledgeGraph:
    return KnowledgeGraph.load(GRAPH_PATH)


def _settings():
    # ANTHROPIC/GEMINI-Keys koennen auch aus st.secrets kommen
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_MODEL",
              "GEMINI_MODEL", "SITE_NAME", "SITE_BASE_URL"):
        val = _secret(k)
        if val and k not in os.environ:
            os.environ[k] = val
    return load_settings()


def tab_graph(kg: KnowledgeGraph, ontology):
    st.subheader("Graph & Fakten")
    stats = kg.stats()
    c1, c2 = st.columns(2)
    c1.metric("Knoten", stats["nodes"])
    c2.metric("Kanten", stats["edges"])

    issues = kg.validate(ontology)
    if issues:
        st.warning("Validierung: " + str(len(issues)) + " Problem(e)")
        for i in issues:
            st.text("• " + i)
    else:
        st.success("Graph ist gueltig (Ontologie).")

    if stats["nodes"]:
        st.graphviz_chart(kg.to_dot(), use_container_width=True)

    with st.expander("Fakten (bestaetigt)"):
        facts = kg.facts()
        if facts:
            st.write("\n".join(f"- {f}" for f in facts))
        else:
            st.info("Noch keine Fakten. Ueber 'Extraktion' befuellen.")

    with st.expander("Graph als JSON-LD bearbeiten (menschliche Bestaetigung)"):
        st.caption("Direktes Bearbeiten des bestaetigten Graphen. "
                   "Nach dem Speichern wird gegen die Ontologie geprueft.")
        current = json.dumps(kg.to_jsonld(ontology), ensure_ascii=False, indent=2)
        edited = st.text_area("JSON-LD", value=current, height=300,
                              key="jsonld_editor")
        if st.button("Speichern", key="save_jsonld"):
            try:
                doc = json.loads(edited)
                new_kg = KnowledgeGraph.from_jsonld(doc)
                problems = new_kg.validate(ontology)
                if problems:
                    st.error("Nicht gespeichert. Probleme:\n"
                             + "\n".join("• " + p for p in problems))
                else:
                    new_kg.save(ontology, GRAPH_PATH)
                    st.success("Gespeichert.")
                    st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"Ungueltiges JSON: {exc}")


def tab_extract(kg: KnowledgeGraph, ontology, settings):
    st.subheader("Extraktion")
    if not settings.has_anthropic:
        st.error("ANTHROPIC_API_KEY fehlt. Extraktion nicht moeglich.")
        return
    st.caption("Claude schlaegt Knoten/Kanten vor. Nichts gilt als wahr, "
               "bis du es uebernimmst.")
    mode = st.radio("Quelle", ["Text einfuegen", "URL laden"], horizontal=True)
    content = ""
    if mode == "Text einfuegen":
        content = st.text_area("Inhalt", height=220)
    else:
        url = st.text_input("URL", value=settings.site_base_url)
        if st.button("Seite laden") and url:
            try:
                content = fetch_page_text(url)
                st.session_state["fetched"] = content
            except Exception as exc:  # noqa: BLE001
                st.error(f"Laden fehlgeschlagen: {exc}")
        content = st.session_state.get("fetched", content)
        if content:
            st.text_area("Geladener Text", value=content[:4000], height=160,
                         disabled=True)

    if st.button("Extrahieren", type="primary") and content.strip():
        complete = lambda p: anthropic_complete(  # noqa: E731
            p, model=settings.anthropic_model, api_key=settings.anthropic_api_key)
        try:
            with st.spinner("Claude extrahiert ..."):
                result = extract_graph(content, ontology, complete)
            st.session_state["extracted"] = result.graph.to_jsonld(ontology)
            st.session_state["extract_warnings"] = result.warnings
        except LLMError as exc:
            st.error(str(exc))

    if "extracted" in st.session_state:
        st.markdown("**Vorschlag:**")
        st.json(st.session_state["extracted"])
        for w in st.session_state.get("extract_warnings", []):
            st.warning(w)
        if st.button("In Graph uebernehmen (bestaetigen)"):
            proposal = KnowledgeGraph.from_jsonld(st.session_state["extracted"])
            kg.merge(proposal)
            kg.save(ontology, GRAPH_PATH)
            del st.session_state["extracted"]
            st.success("Uebernommen und gespeichert.")
            st.rerun()


def tab_llmstxt(kg: KnowledgeGraph, settings):
    st.subheader("llms.txt")
    st.caption("Aufkommende, nicht ratifizierte Konvention. Auswertung durch "
               "KI-Crawler nicht garantiert.")
    text = generate_llms_txt(kg, settings.site_name, settings.site_base_url)
    st.code(text, language="markdown")
    st.download_button("llms.txt herunterladen", data=text, file_name="llms.txt")
    if st.button("Als ./llms.txt speichern"):
        LLMS_TXT_PATH.write_text(text, encoding="utf-8")
        st.success(f"Gespeichert: {LLMS_TXT_PATH}")


def tab_audit(kg: KnowledgeGraph, settings):
    st.subheader("Audit (GEO/AEO)")
    if not settings.has_anthropic:
        st.error("ANTHROPIC_API_KEY fehlt (Judge noetig).")
        return
    engines_available = ["claude"] + (["gemini"] if settings.has_gemini else [])
    st.write("Verfuegbare Engines: " + ", ".join(engines_available))
    if not settings.has_gemini:
        st.caption("Kein GEMINI_API_KEY: nur Claude wird gemessen.")

    probes = load_probes()
    st.write(f"{len(probes)} Proben geladen.")
    missing_expected = [p.id for p in probes if not p.expected]
    if missing_expected:
        st.warning("Proben ohne erwartete Fakten (messen nur Halluzinationen): "
                   + ", ".join(missing_expected))

    est_calls = 2 * len(probes) * len(engines_available)
    st.caption(f"Geschaetzte API-Aufrufe: {est_calls} "
               f"(Obergrenze {settings.max_calls_per_audit}).")

    if st.button("Audit starten", type="primary") and probes:
        engines = {"claude": anthropic_engine(
            settings.anthropic_model, api_key=settings.anthropic_api_key)}
        if settings.has_gemini:
            engines["gemini"] = gemini_engine(
                settings.gemini_model, api_key=settings.gemini_api_key)
        judge = lambda p: anthropic_complete(  # noqa: E731
            p, model=settings.anthropic_model, api_key=settings.anthropic_api_key)
        try:
            with st.spinner("Audit laeuft ..."):
                run = audit_mod.run_audit(
                    engines, probes, kg, judge,
                    max_calls=settings.max_calls_per_audit)
            run.site_name = settings.site_name
            save_audit(run)
            st.success("Audit fertig.")
            st.json(run.summary)
        except LLMError as exc:
            st.error(str(exc))

    hist = audit_history()
    if hist:
        st.markdown("**Verlauf (Durchschnitts-GEO-Score je Engine):**")
        rows = {}
        for h in hist:
            for engine, agg in h.get("summary", {}).items():
                rows.setdefault(engine, []).append(agg.get("avg_geo_score", 0))
        if rows:
            st.line_chart(rows)
        st.caption(f"{len(hist)} Laeufe gespeichert.")


def main():
    if not _password_gate():
        return
    settings = _settings()
    ontology = _ontology()
    kg = _load_graph()

    st.title("🔎 seravel-geo")
    st.caption(f"{settings.site_name} · {settings.site_base_url}")

    t1, t2, t3, t4 = st.tabs(["Graph & Fakten", "Extraktion", "llms.txt", "Audit"])
    with t1:
        tab_graph(kg, ontology)
    with t2:
        tab_extract(kg, ontology, settings)
    with t3:
        tab_llmstxt(kg, settings)
    with t4:
        tab_audit(kg, settings)


if __name__ == "__main__":
    main()
