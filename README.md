# CodeMentor

> **Ein agentisches Multi-Agent-System zur didaktischen Analyse von GitHub Pull Requests**

CodeMentor unterstützt Studierende und Junior-Entwickler dabei, aus ihren eigenen Pull Requests zu lernen. Das System kombiniert mehrere spezialisierte LLM-Agenten, GitHub-Analysen, CI-Ergebnisse und Retrieval-Augmented Generation (RAG), um individuelles, lernorientiertes Feedback zu erzeugen.

Im Gegensatz zu klassischen Code-Review-Assistenten bewertet CodeMentor Pull Requests nicht nur technisch, sondern begleitet den gesamten Lernprozess über mehrere Reviews hinweg. Dazu speichert das System den Lernfortschritt, beantwortet Rückfragen, erstellt Mini-Testate und passt zukünftiges Feedback an den individuellen Wissensstand an.

## Demo

**▶ [Screencast ansehen (3:52 min)](https://ishak-erol.github.io/AAI_CodeMentor/#demo)** — zeigt den vollständigen Ablauf: Analyse eines fehlerhaften Pull Requests, eigenständige Kontextbeschaffung und den Fall, in dem CodeMentor bewusst kein Feedback erzeugt.

Alternativ direkt: [docs/demo.mp4](docs/demo.mp4)

<!-- TODO: Link zur Projekt-Website (GitHub Pages) ergänzen, sobald Pages aktiviert ist -->

---

## Inhalt

- [Schnellstart](#schnellstart)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Browser-UI starten](#browser-ui-starten)
- [CLI-Nutzung](#cli-nutzung)
- [Tests und Code-Qualität](#tests-und-code-qualität)
- [Projektstruktur](#projektstruktur)
- [Features](#features)
- [Architektur](#architektur)
- [Agentenübersicht](#agentenübersicht)
- [Demo-Repository](#demo-repository)
- [Troubleshooting](#troubleshooting)

---

## Schnellstart

Für Eilige — Details in den folgenden Abschnitten.

**Windows (PowerShell)**

```powershell
git clone https://github.com/Ishak-Erol/AAI_CodeMentor.git
cd AAI_CodeMentor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env    # anschließend API_KEY und GITHUB_TOKEN eintragen
python main.py init-db
uvicorn server:app --reload
```

**macOS / Linux (bash)**

```bash
git clone https://github.com/Ishak-Erol/AAI_CodeMentor.git
cd AAI_CodeMentor
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env           # anschließend API_KEY und GITHUB_TOKEN eintragen
python main.py init-db
uvicorn server:app --reload
```

Dann <http://127.0.0.1:8000/threads> öffnen.

---

## Voraussetzungen

| Anforderung | Details |
| ----------- | ------- |
| Python | ≥ 3.11 |
| GitHub Personal Access Token | Scope `repo` — für PR-Daten, Review-Kommentare und den Download der Actions-Artefakte |
| AcademicCloud API-Key | Für LLM-Aufrufe und die RAG-Embeddings (OpenAI-kompatible Chat-API) |

Ohne API-Key startet die Anwendung, liefert aber **kein** LLM-gestütztes Feedback — jeder Agent fällt dann auf sein deterministisches Fallback-Verhalten zurück. Für echte Reviews ist der Key erforderlich.

---

## Installation

```bash
git clone https://github.com/Ishak-Erol/AAI_CodeMentor.git
cd AAI_CodeMentor
```

Virtuelle Umgebung anlegen und aktivieren:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

Abhängigkeiten installieren (`[dev]` enthält pytest, ruff und mypy):

```bash
pip install -e ".[dev]"
```

Datenbankschema anlegen:

```bash
python main.py init-db
```

Die SQLite-Datenbank wird beim Serverstart ohnehin automatisch initialisiert — der Befehl ist nur nötig, wenn ausschließlich die CLI genutzt wird.

---

## Konfiguration

Die Konfiguration erfolgt über Umgebungsvariablen. Vorlage kopieren und ausfüllen:

```powershell
Copy-Item .env.example .env    # Windows
```

```bash
cp .env.example .env           # macOS / Linux
```

`.env` ist per `.gitignore` ausgeschlossen und wird nie eingecheckt.

### Pflichtvariablen

| Variable | Wirkung |
| -------- | ------- |
| `API_KEY` | API-Key der AcademicCloud. Aktiviert automatisch den Live-LLM-Modus **und** die API-Embeddings für RAG. |
| `GITHUB_TOKEN` | GitHub PAT mit `repo`-Scope. |

### Optionale Variablen

Alle Defaults sind in [src/codementor/config.py](src/codementor/config.py) definiert.

| Variable | Default | Wirkung |
| -------- | ------- | ------- |
| `CODEMENTOR_LLM_MODEL` | `devstral-2-123b-instruct-2512` | Verwendetes Chat-Modell |
| `CODEMENTOR_LLM_TEMPERATURE` | `0.2` | Sampling-Temperatur |
| `CODEMENTOR_LLM_BASE_URL` | `https://chat-ai.academiccloud.de/v1` | API-Endpunkt |
| `CODEMENTOR_LLM_ENABLED` | *auto* | Überschreibt die Auto-Aktivierung durch `API_KEY`; `0` schaltet das LLM explizit ab |
| `CODEMENTOR_RAG_ENABLED` | `0` | RAG dauerhaft aktivieren (alternativ pro Lauf via `--rag`) |
| `CODEMENTOR_EMBED_MODEL` | `multilingual-e5-large-instruct` | Embedding-Modell |
| `CODEMENTOR_RAG_PATH` | `.codementor/rag` | Ablage des ChromaDB-Index |
| `CODEMENTOR_RAG_TOP_K` | `4` | Anzahl der Treffer pro Query |
| `CODEMENTOR_RAG_MAX_DISTANCE` | `0.32` | Relevanz-Schwelle (L2-Distanz). Kalibriert für API-Embeddings; beim Hash-Fallback automatisch deaktiviert |
| `CODEMENTOR_RAG_MAX_PAGES` | `15` | Max. Unterseiten pro Doku-Quelle beim Depth-1-Crawl |
| `CODEMENTOR_DOC_URLS` | – | Kommaseparierte Liste zusätzlicher Doku-Quellen |
| `CODEMENTOR_DB_PATH` | `codementor.db` | Pfad zur SQLite-Datenbank |
| `CODEMENTOR_ARTIFACT_NAME` | `codementor-analysis` | Name des CI-Artefakts |
| `CODEMENTOR_WORKFLOW_NAME` | – | Auf einen bestimmten Workflow einschränken |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | Für GitHub-Enterprise-Instanzen |
| `COPILOT_AUTHOR_ALLOWLIST` | `copilot,github-copilot[bot]` | Als Copilot gewertete Kommentar-Autoren |

---

## Browser-UI starten

Umgebungsvariablen laden und Server starten:

```powershell
# Windows (PowerShell) — lädt .env in die aktuelle Session
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
uvicorn server:app --reload
```

```bash
# macOS / Linux
set -a
source .env
set +a

uvicorn server:app --reload
```

Danach öffnen:

```
http://127.0.0.1:8000/threads
```

Die Datenbank wird beim Start automatisch erstellt.

---

## CLI-Nutzung

### Pull Request analysieren

```bash
python main.py --owner OWNER --repo REPOSITORY --pr NUMBER
```

### Mit RAG

```bash
python main.py --owner OWNER --repo REPOSITORY --pr NUMBER --rag
```

### Vollständige Analyse mit Neu-Indexierung

```bash
python main.py --owner OWNER --repo REPOSITORY --pr NUMBER --rag --rag-refresh
```

### Weitere Befehle

| Befehl | Wirkung |
| ------ | ------- |
| `python main.py init-db` | SQLite-Schema anlegen und beenden |
| `python main.py refresh-rag` | Alle Dokumentationsquellen neu indexieren |

Das Ergebnis eines Laufs wird zusätzlich nach `last_run.json` geschrieben.

> **Hinweis:** Reviews laufen ausschließlich live gegen echte GitHub-PRs. Der frühere `--mode mock` wurde entfernt.

---

## Tests und Code-Qualität

```bash
pytest                    # Testsuite (läuft offline, ohne Token und API-Key)
ruff check .              # Linting
mypy src                  # Typprüfung
```

Die Tests nutzen aufgezeichnete GitHub-Payloads aus [tests/fixtures/](tests/fixtures/) und Stub-LLM-Clients — es sind weder Netzwerkzugriff noch Credentials nötig.

Bei jedem Push und Pull Request läuft die Pipeline in [.github/workflows/ci.yml](.github/workflows/ci.yml) mit Ruff, mypy und pytest. Die Ergebnisse werden als Artefakt `codementor-analysis` hochgeladen — genau das Format, das CodeMentor selbst zur Analyse einliest.

---

## Projektstruktur

```text
├── main.py                     CLI-Einstiegspunkt
├── server.py                   ASGI-Einstiegspunkt für uvicorn
├── src/codementor/
│   ├── agents/                 Reflection, Dev-Mentor, Learning, Praise
│   ├── api/                    FastAPI-App, Routen, Templating
│   ├── ci/                     Parser für Ruff, mypy, pytest
│   ├── db/                     SQLModel-Modelle, Engine, Repository
│   ├── github/                 REST-Client, Actions, Artefakte, Copilot
│   ├── rag/                    ChromaDB-Index, Embeddings, Retriever
│   ├── static/                 CSS und HTMX
│   ├── templates/              Jinja2-Templates
│   ├── config.py               Konfiguration aus Umgebungsvariablen
│   ├── graph.py                LangGraph-StateGraph
│   ├── llm.py                  LLM-Clients
│   └── testat.py               Mini-Testate
└── tests/
    ├── fixtures/               Aufgezeichnete GitHub-Payloads
    └── conftest.py             Gemeinsame Test-Fixtures
```

---

## Features

### Multi-Agent-System

CodeMentor verwendet mehrere spezialisierte Agenten, die über LangGraph orchestriert werden: **Reflection Agent**, **Development Mentor Agent**, **Learning Agent** und **Praise Agent**. Der Reflection Agent entscheidet dynamisch, welcher Agent als nächstes ausgeführt wird.

### GitHub-Integration

Analyse echter Pull Requests über die GitHub REST API — Pull Requests, geänderte Dateien, Review-Kommentare, GitHub-Copilot-Reviews und GitHub-Actions-Artefakte.

### CI-Auswertung

CodeMentor verarbeitet automatisch Ergebnisse aus **Ruff**, **mypy** und **pytest**. Die Findings werden vereinheitlicht und in didaktisches Feedback übersetzt.

### Retrieval-Augmented Generation

ChromaDB als Vektordatenbank, indexiert werden u. a. die Dokumentationen von Python, Ruff, mypy und pytest. Bei unbekannten Themen indexiert das System fehlende Dokumentation automatisch nach. Eine kalibrierte Relevanz-Schwelle verwirft unpassende Treffer, statt eine schwache Quelle zu zitieren.

### Lernorientiertes Feedback

Der Mentor erklärt nicht nur Fehler, sondern stellt sokratische Fragen, erklärt Zusammenhänge, verweist auf Dokumentation und passt den Schwierigkeitsgrad an.

### Persistenter Lernfortschritt

Dauerhaft gespeichert werden Reviews, Threads, Lernpunkte, Mini-Testate, Chatverlauf, RAG-Zitate und Verständnisnachweise. Dadurch entsteht ein langfristiges Lernprofil pro Studierendem.

### Browser-Oberfläche

Vollständig lokale Weboberfläche auf Basis von FastAPI, Jinja2 und HTMX. Es wird kein JavaScript-Buildsystem benötigt.

---

## Architektur

```text
        Browser (HTMX)
              │
        FastAPI Backend
              │
       LangGraph StateGraph
              │
     Reflection Agent (LLM)
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
Dev Mentor  Learning   Praise
  Agent      Agent      Agent
              │
       SQLite + SQLModel
              │
       GitHub + ChromaDB
```

### Technologien

| Bereich | Technologie |
| ------- | ----------- |
| Sprache | Python 3.11+ |
| Agenten | LangGraph |
| Backend | FastAPI |
| Frontend | HTMX |
| Datenbank | SQLite + SQLModel |
| Vektordatenbank | ChromaDB |
| HTTP | httpx |
| Testing | pytest |
| Linting / Typing | Ruff, mypy |
| LLM | AcademicCloud (OpenAI-kompatibel) |

---

## Agentenübersicht

**Reflection Agent** — analysiert Pull Request, CI-Findings und Review-Kommentare und entscheidet, welcher Agent ausgeführt wird. Eine deterministische Guardrail beendet die Kette bei trivialen Änderungen (grüne CI, nur Kommentare/Docstrings), damit kein unnötiges Rauschen entsteht.

**Development Mentor Agent** — erzeugt Erklärungen, Lernziele, Mentorfragen, RAG-Zitate und individuelles Feedback.

**Learning Agent** — extrahiert Konzepte, Lernziele und Schwierigkeitsgrad und entscheidet über die Erstellung eines Mini-Testats.

**Praise Agent** — erzeugt positives Feedback, falls keine relevanten Probleme gefunden werden, statt ein leeres Review auszugeben.

### Agentisches Verhalten

CodeMentor trifft eigenständig Entscheidungen über den weiteren Ablauf: evidenzbasiertes Routing, automatische Kontextbeschaffung, On-Demand-Nachindexierung von Dokumentation, Selbstprüfung erzeugter Antworten und adaptive Lernstrategie anhand des bisherigen Lernfortschritts.

Faktenbasierte Entscheidungen erfolgen dabei bewusst **deterministisch im Code** statt per LLM — etwa die Prüfung, ob überhaupt belastbare Evidenz für konkretes Feedback vorliegt. Das macht das Routing unabhängig von Modellgröße und -qualität reproduzierbar.

### Lernprozess

1. Pull Request analysieren
2. individuelles Feedback erzeugen
3. Rückfragen beantworten
4. Verständnis erkennen
5. Lernprofil aktualisieren
6. Mini-Testat erzeugen
7. Testat bewerten
8. zukünftiges Feedback personalisieren

Dadurch entwickelt sich CodeMentor von einem einfachen Review-Tool zu einem langfristigen Lernbegleiter.

---

## Demo-Repository

Zur Demonstration steht ein separates Beispielprojekt zur Verfügung: **[codementor-demo-target](https://github.com/Ishak-Erol/codementor-demo-target)**.

Das Repository enthält einen einfachen Taschenrechner. **Sieben offene Pull Requests** decken jeweils einen anderen Analysefall ab — von typischen Anfängerfehlern bis zu Fällen, in denen CodeMentor bewusst *kein* Feedback erzeugen soll. Sie eignen sich direkt für Live-Demos.

| Pull Request | Branch | Szenario | Erwartetes Ergebnis |
| ------------ | ------ | -------- | ------------------- |
| #1 | `feature/divide` | Fehlender Edge Case (Division durch Null) | pytest schlägt fehl |
| #2 | `feature/parse-age` | Optional-Rückgabe ohne `None`-Prüfung | mypy meldet Typfehler |
| #3 | `chore/statistik` | Unbenutzter Import und `== None` | Ruff meldet Style-Probleme |
| #4 | `refactor/formel` | Schlechte Lesbarkeit | Menschlicher Review-Kommentar |
| #5 | `cleanup/remove-clamp` | Entfernte Funktion mit vergessenem Aufrufer | pytest, mypy und Ruff; demonstriert die automatische Kontextbeschaffung |
| #6 | `docs/kommentare` | Nur erklärende Kommentare ergänzt, CI grün | Die Trivial-Guardrail beendet die Kette (`next_agent="end"`) — kein unnötiges Feedback |
| #7 | `feature/power` | Neue Funktion **mit** passenden Tests, CI grün | Der Praise Agent erzeugt positives Feedback statt eines leeren Reviews |

Die letzten beiden Fälle sind die interessanten für eine Demo: sie zeigen, dass CodeMentor nicht um jeden Preis etwas zu meckern findet. #6 wird deterministisch im Code abgefangen, #7 läuft über den Praise-Pfad.

Für jeden Pull Request läuft dort automatisch eine GitHub-Actions-Pipeline mit Ruff, mypy und pytest, deren Ergebnisse als Artefakt `codementor-analysis` gespeichert werden. CodeMentor lädt dieses Artefakt automatisch herunter und analysiert es.

Analyse eines Demo-PRs — `--pr` auf die gewünschte Nummer aus der Tabelle setzen:

```bash
python main.py --owner Ishak-Erol --repo codementor-demo-target --pr 1
python main.py --owner Ishak-Erol --repo codementor-demo-target --pr 6 --rag
```

### Eigenes Demo-Repository einrichten

Um CodeMentor an eigenen Pull Requests auszuprobieren, brauchst du ein Zielrepository unter deinem eigenen Account — denn CodeMentor liest die CI-Ergebnisse aus einem GitHub-Actions-Artefakt, und Actions laufen nur in Repositories, in denen du sie aktivieren kannst.

**1. Demo-Repository forken**

Auf [codementor-demo-target](https://github.com/Ishak-Erol/codementor-demo-target) oben rechts auf **Fork** klicken. Wichtig: das Häkchen bei *„Copy the `main` branch only"* **entfernen**, damit alle sieben Demo-Branches mitkommen.

**2. GitHub Actions im Fork aktivieren**

In deinem Fork auf den Reiter **Actions** gehen und *„I understand my workflows, go ahead and enable them"* bestätigen. GitHub deaktiviert Workflows in Forks standardmäßig.

**3. Lokal klonen (optional, zum Ansehen und Ändern)**

```bash
git clone https://github.com/DEIN-USERNAME/codementor-demo-target.git
cd codementor-demo-target
git branch -a                      # alle Demo-Branches anzeigen
```

**4. Pull Request öffnen**

Für jeden Demo-Branch einen PR gegen `main` deines Forks aufmachen — entweder über die GitHub-Oberfläche oder direkt:

```bash
gh pr create --base main --head feature/divide --fill
```

Die CI-Pipeline startet automatisch. Warte, bis sie durchgelaufen ist, sonst findet CodeMentor kein Artefakt.

**5. Analysieren lassen**

Jetzt mit deinem eigenen Account als `--owner`:

```bash
python main.py --owner DEIN-USERNAME --repo codementor-demo-target --pr 1 --rag
```

> **Hinweis:** Ein lokaler Klon ist für die Analyse selbst nicht erforderlich — CodeMentor greift ausschließlich über die GitHub API zu, auch bei der automatischen Kontextbeschaffung. Der Klon aus Schritt 3 ist nur nötig, wenn du eigene Branches und Fehlerfälle ergänzen willst.

Alternativ kannst du natürlich auch ein völlig eigenes Python-Projekt verwenden. Es muss lediglich eine GitHub-Actions-Pipeline besitzen, die Ruff, mypy und pytest ausführt und die Ergebnisse als Artefakt `codementor-analysis` hochlädt — die [ci.yml des Demo-Repositories](https://github.com/Ishak-Erol/codementor-demo-target/blob/main/.github/workflows/ci.yml) lässt sich dafür direkt übernehmen.

---

## Troubleshooting

| Symptom | Ursache und Lösung |
| ------- | ------------------ |
| Mentor-Antworten sind leer | `API_KEY` fehlt oder `CODEMENTOR_LLM_ENABLED=0`. Ohne Key läuft das System im Fallback-Modus ohne LLM. |
| `GITHUB_TOKEN is required to analyse a pull request.` | Token nicht gesetzt oder `.env` nicht in die Shell geladen. |
| `No matching workflow run found for the PR.` | Für den PR ist noch keine CI-Pipeline durchgelaufen — im GitHub-Actions-Tab prüfen. |
| `Artifact 'codementor-analysis' not found in workflow run.` | Das Ziel-Repository lädt kein passendes Artefakt hoch. Namen ggf. via `CODEMENTOR_ARTIFACT_NAME` anpassen. |
| `LLM API nicht erreichbar (3 Versuche)` | Vorübergehende Störung der AcademicCloud. Es wird automatisch dreimal wiederholt; danach später erneut versuchen. |
| RAG zitiert keine Quellen | Entweder greift die Relevanz-Schwelle (`CODEMENTOR_RAG_MAX_DISTANCE`) oder der Index ist leer — dann `python main.py refresh-rag` ausführen. |

---

## Lizenz

[MIT](LICENSE)
