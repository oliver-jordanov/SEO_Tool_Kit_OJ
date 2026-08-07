# DataForSEO SEO Research Toolkit

Lokales SEO-Recherchetool für Windows auf Basis der DataForSEO API.

Der aktuelle Stand `v0.4.0` bündelt häufig benötigte Einzelrecherchen in einer einfachen lokalen Browseroberfläche. Die Anwendung speichert Abfragen und Ergebnisse lokal und zeigt die von DataForSEO gemeldeten API-Kosten transparent am jeweiligen Run an.

## Funktionsumfang

### Keyword Overview

- Kennzahlen für ein einzelnes Keyword abrufen
- Standort und Sprache auswählen
- Ergebnisse als lokale Runs speichern
- identische Abfragen über den lokalen Cache wiederverwenden

### SERP Explorer

- organische Google-Suchergebnisse für ein einzelnes Keyword abrufen
- Gerät, Standort, Sprache und Ergebnistiefe auswählen
- organische Treffer und SERP Features darstellen
- optional eine eigene Domain in den Ergebnissen hervorheben

### Backlink Explorer

- Backlink-Profil einer Domain, Subdomain oder URL zusammenfassen
- wichtigste verweisende Domains anzeigen
- begrenzte Liste einzelner Backlinks abrufen

### Gemeinsame Funktionen

- persistente Runs und Detailansichten
- Speicherung von DataForSEO Task-IDs und Ist-Kosten
- redigierte vollständige API-Antworten zur Nachprüfung
- lokale SQLite-Datenbank
- verständliche Fehlerbehandlung
- ausdrückliche Kostenbestätigung vor kostenpflichtigen Live-Abfragen

## Installation unter Windows

Voraussetzung: Python 3.12 oder neuer.

1. Repository herunterladen oder das Release-Archiv entpacken.
2. `setup.bat` doppelklicken.
3. Die neu angelegte `.env` öffnen.
4. `DATAFORSEO_LOGIN` und `DATAFORSEO_PASSWORD` eintragen.
5. `start.bat` doppelklicken.
6. Im Browser `http://127.0.0.1:8765` öffnen.

Die Anwendung bindet ausschließlich an `localhost` und ist dadurch nicht automatisch im lokalen Netzwerk oder im Internet erreichbar.

## DataForSEO-Zugang

Für Live-Abfragen wird ein eigener DataForSEO-API-Zugang benötigt. Die API-Kosten werden von DataForSEO nutzungsabhängig berechnet und sind nicht im Toolkit enthalten.

Zugangsdaten gehören ausschließlich in die lokale `.env`. Diese Datei darf nicht in Git eingecheckt oder weitergegeben werden.

## Lokale Daten und Sicherheit

Folgende lokale Inhalte sind vom Repository ausgeschlossen:

- `.env` und API-Zugangsdaten
- `.venv`
- SQLite-Datenbanken
- Logs und Exporte
- Python-Caches

Vor dem Teilen eigener Kopien sollte trotzdem geprüft werden, dass keine Zugangsdaten, Datenbanken oder gespeicherten API-Antworten enthalten sind.

## Entwicklung und Prüfung

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
alembic current
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## Grenzen von v0.4.0

Das Toolkit ist eine frühe, lokal ausgeführte Version für gezielte Einzelrecherchen. Es ist kein vollständiger Ersatz für Ahrefs, Semrush oder andere umfassende SEO-Plattformen. Insbesondere fehlen derzeit unter anderem Projektverwaltung, umfangreiche Batch-Workflows, Keyword- und Backlink-Gap-Analysen sowie formatierte Exporte.

Die Ergebnisse stammen aus der DataForSEO API. Verfügbarkeit, Datenabdeckung, Preise und Antwortformate können sich auf Seiten des API-Anbieters ändern.

## Projektstatus

`v0.4.0` ist die erste intern teilbare Version mit funktionsfähigem Keyword Overview, SERP Explorer und Backlink Explorer.

Das Projekt wurde von Oliver Jordanov in Eigeninitiative und außerhalb der für WOXOW abgerechneten Projektzeit entwickelt. Es handelt sich derzeit nicht um ein offizielles WOXOW-Produkt und es besteht kein verbindliches Support- oder Weiterentwicklungsversprechen.

## Nutzungsrechte

Für dieses Repository wurde derzeit keine Open-Source-Lizenz vergeben. Der öffentlich sichtbare Quellcode darf dadurch nicht automatisch kopiert, verändert oder weiterverbreitet werden. Alle Rechte bleiben vorbehalten.
