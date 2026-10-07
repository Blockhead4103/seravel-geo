"""Seravel GEO: Knowledge-Graph und GEO/AEO-Audit fuer eine einzelne Website.

Separates Werkzeug neben Seravel. Baut aus Website-Inhalten einen
eingebetteten Knowledge-Graph (JSON-LD + NetworkX), erzeugt daraus eine
llms.txt und misst, wie KI-Assistenten Fragen zur Website beantworten
(Abgleich gegen bestaetigte Fakten, wie in Seravel).
"""

__version__ = "0.1.0"
