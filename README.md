# DataForSEO Research Toolkit — Phase 1

Lokales Windows-Grundgerüst gemäß `ARCHITECTURE.md` und `ROADMAP.md`. Es enthält FastAPI/Jinja, SQLite/SQLAlchemy/Alembic, einen zentralen DataForSEO-Client, Secret-Redaction, kanonische Request-Hashes, TTL-Cache, persistente Runs, komprimierte Rohantworten und ein Ist-Kostenjournal.

## Installation unter Windows

Voraussetzung: Python 3.12 oder neuer.

1. ZIP entpacken.
2. `setup.bat` doppelklicken.
3. `.env` öffnen und `DATAFORSEO_LOGIN` sowie `DATAFORSEO_PASSWORD` eintragen.
4. `start.bat` doppelklicken.
5. Browser: `http://127.0.0.1:8765`

`start.bat` bindet ausschließlich an localhost. `.env`, Datenbank, Logs und Exporte sind ausgeschlossen.

## Sicherer erster Test

Die Startseite bietet einen Keyword-Overview-Smoke-Test. Ein Cache-Miss wird nur mit gesetzter Kostenbestätigung gesendet. Der erwartete Minimalpreis ist ungefähr 0,01212 USD; maßgeblich gespeichert wird `tasks[].cost`.

Nach dem ersten erfolgreichen Abruf denselben Begriff erneut **ohne** „Cache bewusst umgehen“ absenden. Der zweite Run muss `Cache-Hit, keine API-Kosten` anzeigen und erzeugt keinen zweiten API Request.

Die wichtigsten Keyword-Werte erscheinen unmittelbar nach dem Abruf. Über die verlinkte Run-ID lassen sich gespeicherte Ergebnisse später erneut öffnen; dort ist zusätzlich die vollständige persistierte API-Antwort aufklappbar.

## SERP Explorer v1

Der zweite Slice nutzt Google Organic Live Advanced für einzelne, ausdrücklich bestätigte Abfragen. Gerät, Top 10/100, Location, Sprache und optionale eigene Domain werden gespeichert. Organische Treffer und SERP Features liegen normalisiert in SQLite; Task-ID, Ist-Kosten und die redigierte Rohantwort bleiben am Run verfügbar. Es gibt keinen automatischen Retry und keinen SERP-Cache.

Nach Installation des Update-Pakets einmal `setup.bat` ausführen. Dadurch wird auch Migration `0002` für bestehende Datenbanken angewendet; vorhandene Keyword-Overview-Runs bleiben erhalten.

## Entwicklung und Prüfung

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
alembic current
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## Phase-1-Grenze

Die Tabellen für Projekte, Wettbewerber und persistente Jobs sind angelegt, ihre CRUD-/Worker-Funktionen folgen planmäßig in Phase 2 beziehungsweise Phase 6. Fachliche Keyword-Result-Mappings, SERP-, Backlink- und Excel-Tabellen werden mit ihren Modulen ergänzt; Phase 1 übermodelliert diese Daten bewusst noch nicht.
