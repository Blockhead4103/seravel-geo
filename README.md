# seravel-geo

*Von Lancashire Digital. Separates Werkzeug neben Seravel.*

Baut aus den Inhalten **einer** Website (Default: lancashire-digital.ch) einen
**Knowledge-Graph**, erzeugt daraus eine **llms.txt** und **misst**, wie gut
KI-Assistenten Fragen zu dieser Website beantworten (GEO/AEO). Alles lokal
lauffaehig, gratis deploybar auf Streamlit Community Cloud, kein Graph-Server.

## Warum getrennt von Seravel

Seravel ist ein **mandantenfaehiges Kundenportal**, das das Delta zwischen
bestaetigten Quell-Fakten und KI-Antworten fuer **mehrere Kunden** misst
(Supabase, Row Level Security, 2FA, Review, Berichte). seravel-geo ist das
Gegenstueck fuer die **eigene** Seite: **ein Mandant**, Fokus auf
**Produktion/Optimierung** (Graph, llms.txt) plus eine schlanke Messung.
Andere Aufgabe, anderes Mandantenmodell, anderer Datenspeicher. Darum ein
eigenes Repo statt Einbau in Seravel. Die Mess-Methodik ist aber bewusst an
Seravel angelehnt (Antwort in Aussagen zerlegen, gegen bestaetigte Fakten
pruefen, Abweichungen = falsch + unbelegt + fehlend).

## Die vier Bausteine (gegenueber dem urspruenglichen 4-Tool-Plan)

| Plan | Hier umgesetzt als |
|---|---|
| Claude: Graph bauen (Extraktion, Ontologie) | `geo/extract.py` + `ontology.yaml` + `geo/graph.py` |
| Streamlit: Dashboard | `app.py` (Graph ansehen, Extraktion testen, llms.txt, Audit) |
| Gemini: synthetische Audits (GEO-Score, Halluzinationen) | `geo/audit.py` (Engines pluggbar: Claude und/oder Gemini; Judge: Claude) |
| GitHub: orchestrieren/deployen | `.github/workflows/audit.yml` (woechentlich + bei Push) |

**Bewusste Abweichung vom Plan (First Principles):** statt **Neo4j** ein
**eingebetteter** Graph (JSON-LD + NetworkX). Neo4j braucht einen laufenden
Server und ist auf Streamlit Community Cloud nicht gratis betreibbar; fuer eine
Einzelsite ist das unnoetiger Betrieb. JSON-LD ist zugleich das Format, das
Suchmaschinen/KI ohnehin verstehen.

## Ablauf

1. **Extraktion** (Reiter «Extraktion»): Text einfuegen oder URL laden. Claude
   schlaegt Knoten/Kanten **streng nach Ontologie** vor. Nichts gilt als wahr,
   bis du es uebernimmst (menschliche Bestaetigung, wie in Seravel).
2. **Graph** (Reiter «Graph & Fakten»): ansehen, als JSON-LD direkt bearbeiten,
   gegen die Ontologie pruefen. Aus dem Graphen entstehen die «Fakten».
3. **llms.txt** (Reiter «llms.txt»): deterministisch aus dem Graphen erzeugt,
   herunterladen oder als Datei speichern.
4. **Audit** (Reiter «Audit»): Proben (Fragen) gegen die Engines laufen lassen.
   Jede Antwort wird gegen die Fakten geprueft: Abdeckung, Halluzinationen,
   GEO-Score. Der Verlauf zeigt, ob der Score ueber die Zeit steigt.

## Architektur

```
                 ┌─────────────────────────┐
  Website  ─────▶│ extract.py (Claude)      │──▶ Vorschlag (Knoten/Kanten)
  (Text/URL)     └─────────────────────────┘        │  Mensch bestaetigt
                                                     ▼
                                      data/graph.jsonld  (JSON-LD, versioniert)
                                                     │
                 ┌───────────────┬───────────────────┼───────────────────┐
                 ▼               ▼                   ▼                    ▼
           graph.py        llmstxt.py            audit.py             app.py
         (NetworkX,       (llms.txt aus        (Engines fragen,     (Streamlit-
          Validierung,     dem Graphen)         Judge bewertet       Dashboard)
          Fakten, DOT)                          vs. Fakten)
                                                     │
                                            data/audits/*.json (Verlauf)

  GitHub Action (audit.yml): bei Push → llms.txt neu; woechentlich → Audit;
  committet Ergebnisse zurueck (zugleich Persistenz, da Streamlit Cloud ein
  fluechtiges Dateisystem hat).
```

## Einrichtung

Menuebezeichnungen von GitHub/Streamlit/Anbietern koennen sich aendern; im
Zweifel deren Doku ansehen.

### 1. Lokal
```
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # ANTHROPIC_API_KEY eintragen
streamlit run app.py
```

Ohne API-Schluessel funktionieren weiterhin: Graph ansehen/bearbeiten,
Validierung, Fakten, llms.txt. Extraktion braucht `ANTHROPIC_API_KEY`, das
Audit zusaetzlich (fuer den Judge) ebenfalls Anthropic.

### 2. CLI (auch fuer die Action)
```
python cli.py validate                 # Graph gegen Ontologie pruefen
python cli.py facts                     # bestaetigte Fakten ausgeben
python cli.py llmstxt                   # llms.txt neu erzeugen
python cli.py extract --url https://lancashire-digital.ch --merge
python cli.py audit                     # GEO-Audit (kostet API-Aufrufe)
```

### 3. Online (Streamlit Community Cloud)
1. Repo auf share.streamlit.io verbinden, Hauptdatei `app.py`.
2. **Advanced settings → Secrets** setzen:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "..."            # sonst ist das Dashboard offen zugaenglich
   # optional:
   GEMINI_API_KEY = "..."
   ANTHROPIC_MODEL = "claude-opus-5-5"
   SITE_NAME = "Lancashire Digital"
   SITE_BASE_URL = "https://lancashire-digital.ch"
   ```
3. **Warum nicht Vercel?** Streamlit braucht einen dauerhaft laufenden Server
   mit WebSocket; Vercels kurzlebige Functions passen dafuer nicht.

### 4. GitHub Action
- Secrets: `ANTHROPIC_API_KEY`, optional `GEMINI_API_KEY`.
- Variablen (optional): `ANTHROPIC_MODEL`, `GEMINI_MODEL`, `MAX_CALLS_PER_AUDIT`.
- Die Action erzeugt bei Push llms.txt neu (kostenlos) und faehrt woechentlich
  das Audit (kostenpflichtig), dann committet sie `llms.txt` und
  `data/audits/` zurueck.

## Modelle & SDKs (bitte pruefen)

- **Anthropic** (Extraktion + Judge): Default-Modell `claude-opus-5-5`, per
  `ANTHROPIC_MODEL` aenderbar. Guenstiger und fuer Extraktion meist
  ausreichend: `claude-sonnet-5-5` oder `claude-haiku-5-5`. Modell-IDs aendern
  sich; gegen die aktuelle Anthropic-Doku pruefen.
- **Gemini** (optionale Audit-Engine): nutzt `google-generativeai`. Diese SDK
  und die Modellnamen aendern sich haeufiger; gegen ai.google.dev pruefen. Ohne
  `GEMINI_API_KEY` wird nur Claude gemessen.

## GEO-Score (transparent, handgewaehlt)

Pro Probe mit erwarteten Fakten:
- **Abdeckung** = genannte erwartete Fakten / erwartete Fakten.
- **Halluzinationen** = widersprechende + unbelegte Aussagen.
- **GEO-Score** = Abdeckung in % minus Strafpunkte
  (widersprechend −15, unbelegt −6 je Aussage), begrenzt auf 0..100.

Die Gewichte stehen in `geo/audit.py` und sind **von Hand gewaehlt, nicht
wissenschaftlich ermittelt**. Ohne erwartete Fakten misst eine Probe nur
Halluzinationen, nicht die Abdeckung.

## Grenzen (ehrlich)

- Der mitgelieferte Graph (`data/graph.jsonld`) ist ein **Platzhalter ohne
  verifizierte Fakten**. Erst befuellen und bestaetigen, bevor eine llms.txt
  veroeffentlicht wird.
- **llms.txt** ist eine aufkommende, **nicht ratifizierte** Konvention. Ob und
  wie KI-Crawler sie auswerten, ist nicht garantiert.
- Der **Judge ist selbst ein LLM** (Claude); Fehlurteile bei der Zerlegung in
  Aussagen sind moeglich. Score als Richtung lesen, nicht als exakte Wahrheit.
- Gemessen wird die **API** der Anbieter; deren Consumer-Apps koennen anders
  antworten.
- Das **Laden von Webseiten** (`fetch_page_text`) und die **echten API-Aufrufe**
  sind in der Entwicklungsumgebung **nicht live getestet** (kein Internet). Die
  Logik ist mit simulierten Antworten getestet (`tests/`, 41 Tests).
- Kleine Proben-Stichproben schwanken; Veraenderungen unter etwa 10 Punkten
  vorsichtig lesen.
- Robots.txt und Nutzungsbedingungen beim Laden beachten.

## Tests
```
pip install pytest
python -m pytest
```
Alle HTTP-/LLM-Aufrufe sind in den Tests simuliert; es werden keine echten
APIs aufgerufen und keine Kosten verursacht.

## Dateien

| Pfad | Zweck |
|---|---|
| `app.py` | Streamlit-Dashboard (4 Reiter) |
| `cli.py` | Kommandozeile (validate, facts, llmstxt, extract, audit) |
| `ontology.yaml` | erlaubte Knoten-/Beziehungstypen (an schema.org angelehnt) |
| `geo/config.py` | Konfiguration aus Env/.env |
| `geo/llm.py` | LLM-Adapter (Anthropic, Gemini) + JSON-Parsing |
| `geo/ontology.py` | Ontologie laden/pruefen |
| `geo/extract.py` | Inhalt → Graph-Vorschlag (Claude); Seite laden |
| `geo/graph.py` | Knowledge-Graph: JSON-LD ↔ NetworkX, Fakten, DOT |
| `geo/llmstxt.py` | llms.txt aus dem Graphen |
| `geo/audit.py` | Proben, Judge, GEO-Score |
| `geo/store.py` | Proben laden, Audit-Laeufe speichern/lesen |
| `data/graph.jsonld` | der bestaetigte Graph (Platzhalter) |
| `data/probes.yaml` | Audit-Fragen |
| `.github/workflows/audit.yml` | Action: llms.txt + Audit |
| `tests/` | pytest, alle externen Aufrufe simuliert |
