# ProcWorks · Correctness by Construction

> Open-Source-Werkzeug zur **stabilen Prozessmodellierung**, **Instanzerstellung/-ausführung** und **intuitiven, modernen Bedienung** – auf Basis der Forschungsidee *Correctness by Construction* (ADEPT2, Universität Ulm), mit kompromisslosem Fokus auf Benutzerführung im Frontend bei voller Konsistenz im Backend.

[![License: BUSL-1.1](https://img.shields.io/badge/License-BUSL--1.1-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-konzept%20%2B%20prototyp-blue.svg)](docs/Architektur-Konzept-Prozessmodellierung.md)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-informational.svg)](.github/workflows/ci.yml)

---

## Worum geht es?

Dieses Projekt entwickelt ein Werkzeug zur Modellierung und Ausführung von
Geschäftsprozessen (BPMN 2.0 als fachliche Basis). Leitidee sind **drei Säulen**:

1. **Stabile Modellierung** – jede Änderung am Modell führt **immer** zu einem
   syntaktisch korrekten und ausführbaren Modell (*Correctness by Construction*).
2. **Instanzerstellung & -ausführung** – aus freigegebenen Modellen werden
   konsistente Prozessinstanzen erzeugt und überwacht.
3. **Intuitive, moderne Bedienung** – die bewusste Differenzierung gegenüber
   klassischen, technisch geprägten Workflow-Werkzeugen: vorne komfortabel und
   modern, hinten kompromisslos stabil.

Das vollständige Architektur-Konzept liegt in
[docs/Architektur-Konzept-Prozessmodellierung.md](docs/Architektur-Konzept-Prozessmodellierung.md).

## Schnellstart: In 15 Minuten einsatzbereit

> ⚠️ **Haftungsausschluss – bitte vor der Inbetriebnahme lesen.** ProcWorks wird
> **„wie besehen", ohne jede Gewährleistung und ohne jede Haftung**
> bereitgestellt. Inbetriebnahme und Nutzung erfolgen **ausschließlich auf
> eigenes Risiko**. Wir haften – im größtmöglichen gesetzlich zulässigen Umfang –
> **für keinerlei Schäden**, weder im Zusammenhang mit der **Inbetriebnahme**
> (z. B. an Servern, Hardware, Betriebssystemen, paralleler/Drittsoftware,
> Netzwerken oder Infrastruktur) noch mit der **Nutzung** (z. B. Verlust oder
> Beschädigung von Daten und fehlerhafte Geschäftsprozesse). Prüfen Sie das
> Werkzeug zuerst in einer **isolierten Testumgebung** und legen Sie **Backups**
> an. Vollständiger Text: [DISCLAIMER.md](DISCLAIMER.md).

> Für mittelständische Unternehmen **ohne eigene IT-Abteilung**. Sie brauchen
> kein Vorwissen – nur einen Rechner mit Internet. ProcWorks startet als ein
> einziger, in sich geschlossener Container-Verbund (Datenbank + Server +
> Oberfläche); Sie installieren **eine** Voraussetzung und führen **einen**
> Befehl aus.

### Standardfall: Windows Server (nichts vorinstalliert)

Auf einem frischen Windows Server sind genau **drei kostenlose Programme** nötig.
Jedes wird per Mausklick installiert – die ausführliche, bebilderte
Schritt-für-Schritt-Anleitung steht in
[docs/Windows-Server-Setup.md](docs/Windows-Server-Setup.md).

1. **WSL2 aktivieren** – einmalig in der PowerShell (als Administrator):
   `wsl --install`, danach den Server neu starten.
2. **Docker Desktop** installieren – von <https://www.docker.com/products/docker-desktop/>,
   bei der Installation „Use WSL 2" aktiviert lassen und einmal starten, bis
   „Engine running" erscheint. *(Docker ist die Verpackung, in der ProcWorks
   ausgeliefert wird – damit entfällt jede manuelle Einrichtung von Datenbank
   und Server.)*
3. **Git** installieren – von <https://git-scm.com/download/win> (Standardoptionen
   genügen).

Danach in der PowerShell **diese vier Zeilen** ausführen (holt ProcWorks und
startet alles):

```powershell
cd C:\
git clone https://github.com/tobiasHaecker/procworks.git ProcWorks
cd C:\ProcWorks
docker compose -f deploy/docker-compose.full.yml up --build -d
```

Fertig. Im Browser `http://localhost` öffnen – es erscheint das Login-Fenster.

#### Erste Anmeldung als Administrator

- **Login:** `admin`
- **Passwort:** ein **einmaliges Start-Passwort**, das beim allerersten Start
  automatisch erzeugt und **ins Server-Log geschrieben** wird. Beim ersten
  Anmelden verlangt das System sofort ein eigenes, neues Passwort.

So lesen Sie das Start-Passwort aus dem Server-Log – in der **PowerShell**, aus
dem Ordner `C:\ProcWorks`:

```powershell
docker compose -f deploy/docker-compose.full.yml logs api | Select-String "Initial admin"
```

Die gesuchte Zeile sieht so aus (das Passwort steht hinter `temporary password=`):

```text
Initial admin account created (login='admin', temporary password='…').
```

> Tipp: Wer das Passwort lieber vorab selbst festlegt, setzt es in der
> Compose-Datei über `PROCWORKS_ADMIN_PASSWORD` (siehe
> [Windows-Anleitung, Abschnitt 5](docs/Windows-Server-Setup.md)). Dann entfällt
> der Blick ins Log.

### macOS / Linux (zum Ausprobieren)

Voraussetzung ist nur **Docker** (Docker Desktop auf macOS, Docker Engine unter
Linux). Dann:

```bash
git clone https://github.com/tobiasHaecker/procworks.git
cd procworks
docker compose -f deploy/docker-compose.full.yml up --build -d
# Oberfläche: http://localhost   ·   Login: admin
# Das einmalige Start-Passwort steht im Server-Log (hinter "temporary password="):
docker compose -f deploy/docker-compose.full.yml logs api | grep "Initial admin"
```

### Sofort ausprobieren: Beispieldaten laden

Damit alle Funktionen **sofort greifbar** sind, bringt ProcWorks fertige
Beispieldaten mit (eine Organisation „Acme", zwei Prozesse und drei laufende
Instanzen). So laden Sie sie:

1. Als **Administrator** anmelden.
2. In die Sicht **Monitoring** wechseln, ganz unten zum Bereich
   **„Wartung (Administrator)"** scrollen.
3. **„Beispieldaten laden"** klicken und bestätigen.

Derselbe Bereich enthält **„Auf Null zurücksetzen"**, um jederzeit wieder mit
einem leeren System zu starten. Beides ist **nur für Administratoren** sichtbar.

Nach dem Laden können Sie sich mit den **Testbenutzern** anmelden (Passwort für
alle: `demo-procworks`):

| Login | Person | Rolle | Sieht / kann |
| --- | --- | --- | --- |
| `mara.modell` | Mara Modell | Modellierer | Prozesse modellieren, Daten/Organisation pflegen |
| `erika.sander` | Erika Sander | Bearbeiter | Aufgaben erledigen (hat offene Urlaubsanträge) |
| `tom.berger` | Tom Berger | Bearbeiter (Leitung) | Genehmigungen erteilen |
| `vera.viewer` | Vera Viewer | Leser | Monitoring nur ansehen |

> Die Testbenutzer existieren erst **nach** dem Laden der Beispieldaten und nur
> im Login-Betrieb (Standard im mitgelieferten Stack). Bitte vor dem
> Produktivbetrieb über **„Auf Null zurücksetzen"** entfernen.

Eine Kurzanleitung speziell für Mitarbeiter (Anmelden + Aufgaben bearbeiten)
liegt in [docs/Mitarbeiter-Anleitung.md](docs/Mitarbeiter-Anleitung.md); eine
Schritt-für-Schritt-Anleitung für Modellierer in
[docs/Modellierer-Anleitung.md](docs/Modellierer-Anleitung.md). Den Einstieg in
die **gesamte Dokumentation nach Rolle** bietet
[docs/README.md](docs/README.md). Im Web-Client führt zusätzlich die Sicht
**„Hilfe"** durch alle Sichten und erklärt die Regel-Codes.

## Correctness by Construction (Kernprinzip)

Es gilt durchgängig eine **Korrektheitsinvariante I**: Jeder Bearbeitungsschritt
ist eine korrektheitserhaltende Transformation `apply: (Model_gültig, Op, Params) ? Model_gültig | Rejected`.
Es gibt **zwei Stufen**:

- **Stufe A – Struktur** (immer erzwungen je Operation): Kontrollfluss (K),
  Datenfluss (D), Ressourcen/Bearbeiter (Z).
- **Stufe B – Ausführbarkeit/Freigabe**: Dienstbindung (B1), Bearbeiterzuordnung
  (B2), Datenbindung (B3).

Laufende Instanzen werden bei einer neuen Revision **individuell** und konsistent
nach den Migrationskriterien (M1–M5) übernommen oder bleiben stabil auf ihrer
Version.

## Klickbarer UI-Prototyp

Ein eigenständiger Oberflächen-Prototyp (kein Build, keine Installation)
demonstriert die Benutzerführung mit drei Ansichten:

| Ansicht | Inhalt |
| --- | --- |
| **Modellierung** | BPMN-Canvas mit geführten „+"-Operationen; jede Operation erhält die Struktur (Stufe A), Verzweigungen werden als balancierte Blöcke eingefügt; Bindungspanel für B1/B2/B3 mit Live-Freigabestatus. |
| **Monitoring** | Live-Prozesslandkarte mit Status-Overlay, KPIs, Instanzliste mit Filtern, Detail-Drawer mit Zeitreise. |
| **Revisionsübernahme** | Geführter Migrations-Assistent (v3?v4) mit Diff, M1–M5-Auswertung, Einzel- und Sammelübernahme. |

> **Live-Aktualisierung:** Wird der Fortschritt einer Aktivität/Instanz
> aktualisiert, aktualisieren sich Aufgabenlisten, Ausführen-Sicht und
> Monitoring im Web-Client automatisch (Hintergrund-Polling von
> `GET /monitoring/revision`). Die aktive Sicht überlebt zudem einen
> Seiten-Reload (Persistenz im Browser).

**Öffnen:** [prototype/index.html](prototype/index.html) direkt im Browser per Doppelklick
oder über die VS-Code-Erweiterung „Live Server".

## Backend-Kern (Walking Skeleton)

Unter [core/](core/) liegt der lauffähige, **headless** Engine-Kern in Python
(Roadmap-Schritte 0–11 mit Activity Repository, Daten-Connectoren,
BPMN-Import/Export und schlankem Web-Client). Er belegt das
Kernprinzip
praktisch: Ein Schema lässt sich nur über geprüfte Operationen verändern, jede
Operation validiert vor dem Commit gegen K1-K3, D1-D4, Z1-Z4, A1-A3, C1-C9 und die
Kompositionsregeln H1-H4/F1-F4.

- **Meta-Modell + Validator (K1–K3, D1–D4, Z1–Z4, A1–A3, C1–C9, H1–H4/F1–F4) + Change Operations** (`serial`/`parallel`/`conditional insert`, `rename_node`, `delete_node`, `add_data_element`, `connect_data`, `add_role`/`add_org_unit`/`add_agent`, `assign_service`, `assign_staff_rule`, `add_activity_template`, `register_connector`, `bind_external_data`, `bind_sql_select`/`bind_sql_write`, `insert_subprocess`, `convert_activity_to_subprocess`, `set_subprocess_binding`, `set_library_subprocess`, `link_follow_up`, `link_org_model`/`unlink_org_model`, `release`) + **BPMN-Import/Export** (`export_bpmn`/`import_bpmn`). `delete_node` entfernt Aktivitäten/Teilprozesse auf serieller Strecke (Lücke wird geschlossen) bzw. bei einem Split den gesamten SESE-Block; löscht man den letzten Knoten eines Verzweigungszweigs, wird der Zweig entfernt und – falls nur noch einer übrig bleibt – die ganze Verzweigung aufgelöst; `rename_node` ändert nur die Bezeichnung — beides über Validate-before-Commit.
- **Datenfluss**: D1 (Schreiben-vor-Lesen auf allen Pfaden), D2 (keine konkurrierenden AND-Schreibzugriffe), D3 (Typkonformität), D4 (Wohlgeformtheit).
- **Ressourcen/BZR**: Z1 (wohlgeformte Regel + existierende Org-Referenzen, inkl. Vorgesetzter/Vertreter als Org-Stammdaten), Z2 (auflösbar/nicht-leer), Z3 (`NodePerformingAgent`-Rückbezüge garantiert-vorher), Z4 (Dienst-/BZR-Konsistenz). Eine `ORG_UNIT`-Regel adressiert wahlweise nur die Abteilung oder rekursiv alle untergeordneten Bereiche.
- **Geteilte Organisationsmodelle**: eine Organisation kann **modellübergreifend** geteilt werden — einmal als eigenständige Stammdaten-Entität modelliert (`/org-models`), von mehreren Schemata referenziert (`org_model_id`) und beim Laden per **Hydration** an der API-Grenze eingespielt (Validator/Ausführung bleiben unverändert). Verknüpfen/Lösen nur in ENTWURF; jede Org-Änderung wird gegen **alle** referenzierenden Schemata revalidiert und bei Bruch (Z2) mit HTTP 422 abgelehnt (CbC über die Modellgrenze).
- **Activity Repository**: A1 (gebundene Vorlage existiert), A2 (`automatic`-Flag passt zum Executor), A3 (typkonforme Bindung der Vorlagen-Schnittstelle). Vorlagen sind wiederverwendbare Bausteine mit typisierter I/O-Schnittstelle (Plug-&-Play-Modellierung).
- **Daten-Connectoren (C1–C9)**: Datenelemente sind `INSTANCE` (in der Instanz) oder `EXTERNAL` (über einen Connector aus DB/Fachanwendung aufgelöst). C1–C3 für die **Record-Bindung** (registrierter Connector, `INSTANCE`-Schlüsselelement, nicht-leere Entität). Ein **Data Access Layer** (`dal.py`) mit schmaler Connector-SPI (`read`/`write`/`query`, MS SQL/MySQL/Dynamics 365/SAP/`CUSTOM`) löst externe Elemente zur Laufzeit auf — stets **parametrisiert** (kein Injection-Risiko), Secrets nur serverseitig. Darüber hinaus gibt es eine **typ- und kardinalitätssichere Skalar-Anbindung per SQL** (Correctness by Construction **auch für die SQL-Erzeugung**): statt Freitext-SQL wird ein `SELECT`/`UPDATE` aus einer strukturierten, entscheidbaren Skizze **deterministisch kompiliert** (`compile_select`/`compile_update`, injektionssicher über Bezeichner-Whitelist + Bind-Parameter) und CbC-geprüft, sodass das Ergebnis **typgleich** zum Datenelement ist (C4/C7) und **höchstens eine** Zeile trifft (C6/C9), mit typkonformen, rechtzeitig versorgten Filtern (C5/C8). Ein geführter Web-Assistent („SQL-Select"/„SQL-Write") mit Spalten-Introspektion, Live-Vorschau und Typ-/Kardinalitäts-Ampel modelliert die Bindung. Derselbe strukturierte Zugriff wird vom **OData-v4-Connector** (`odata.py`, Dynamics 365 / SAP Gateway) über `$select`/`$filter`/`$orderby`/`$top`/`$count`/`$apply` bzw. einen keyed `PATCH` bedient — **dieselbe SPI**, sodass Kern, Regeln und GUI unverändert bleiben.
- **Offene Integrationsschicht (`/v1`)**: eine maximal offene, robuste API zur Anbindung fremder Tools, abgesichert über eine **Maschinen-Rolle `integration` mit Scopes** und **Idempotency-Keys**. **Inbound**: Tools starten Instanzen und schließen Aufgaben inkl. Daten ab (`/v1/schemas/{id}/instances`, `…/complete`, `…/data`); XOR-Verzweigungen entscheidet die Engine automatisch aus den Daten (K7). **Outbound – Pull**: eine automatische Aktivität wird zur **External Task**, die ein Worker per `fetch-and-lock` abholt und zurückmeldet (Lock/Backoff/Inzident, Exactly-once). **Outbound – Push (`HTTP_PUSH`)**: ProcWorks pusht das Eingabe-Datenpaket bei Aktivierung an ein serverseitig konfiguriertes Tool-Endpoint (`PROCWORKS_PUSH_ENDPOINTS`); das Tool meldet das Ergebnis per Callback-Token über den regulären Completion-Endpunkt zurück. **Webhooks**: signierte Ereignis-Abonnements (`instance.*`/`task.*`) über eine transaktionale **Outbox** (HMAC, Retry, Circuit-Breaker, SSRF-Allowlist). Die Integrationsschicht treibt den Kern nur über bestehende, geprüfte Operationen — der Kern bleibt rein. Rezepte & Endpunkt-Referenz: [docs/Integrations-Leitfaden.md](docs/Integrations-Leitfaden.md).
- **Komposition**: H1–H4 (Sub-Prozesse: RELEASED+gepinntes Ziel, typkonformes Mapping, azyklische Hierarchie, immutable Version), F1–F4 (Folgeprozesse: Zielexistenz, Handover-Konformität, Entkopplung, wohlgeformte `CONDITIONAL`-Bedingung).
- **Execution Engine**: Instanziierung freigegebener Schemata, ADEPT-Knoten-/Kantenmarkierung (NS/ES), Worklist, parallele AND-Zweige, XOR-Branch-Entscheidung; jede Endmarkierung lässt alle Knoten `COMPLETED` oder `SKIPPED`. Ein `SUBPROCESS`-Knoten startet zur Laufzeit eine Kind-Instanz seines gepinnten Zielschemas (mit Ein-/Ausgabe-Mapping) und join't sie beim Abschluss zurück; beim Abschluss einer Instanz starten ihre Folgeprozesse neue Instanzen — `ON_COMPLETE` immer, `CONDITIONAL` nur bei wahrer Bedingung (sicherer Ausdrucks-Evaluator, ohne `eval`); `ASYNC` entkoppelt vollständig (F3), `SYNC` koppelt über eine Ursprungs-Instanz-ID.
- **Bearbeiter-Aufgabenliste**: zur Laufzeit löst der Kern die BZR eines aktiven Schritts konkret auf (Rolle/Abteilung — optional rekursiv —, `NodePerformingAgent` über den tatsächlichen Bearbeiter, `AND`/`OR`/`EXCEPT`) und erweitert um die transitive Vertreterkette. Eine an Abteilung/Rolle gerichtete Aufgabe erscheint bei allen Personen, wird aber von genau einer erledigt; ein Abschluss durch eine nicht berechtigte Person wird mit HTTP 409 abgelehnt und der Bearbeiter in `performed_by` vermerkt (`GET /agents/{id}/tasks`, `GET /instances/{id}/tasks`).
- **FastAPI** als einzige Eintrittstür (API-first); ungültige Operationen ? HTTP 422, unzulässige Laufzeitschritte ? HTTP 409. Eine permissive CORS-Middleware öffnet die API für den Browser-Client.
- **Authentifizierung & Rollen (optional)**: ein austauschbarer `AuthBackend` (analog zum `SchemaStore`) sichert die API am Boundary. Standardmäßig läuft sie **offen** (Entwicklung: alle Rollen, kein Login); mit `PROCWORKS_AUTH=token` greift ein Token-Backend (Bearer-Token aus `PROCWORKS_TOKENS`, nur als SHA-256-Digest gehalten). Für Deployments ohne externen Identity-Provider gibt es zusätzlich ein **Passwort-Login** (`PROCWORKS_AUTH=password`): Login-Name `vorname.nachname` aus dem Agentennamen vorgeschlagen, Zugangsdaten in einem separaten `CredentialStore` (nicht im Modell), `hashlib.scrypt`-Hashing, Initialpasswort mit erzwungener Änderung beim ersten Login, Session-Bearer-Token. Vier grobe Rollen — `admin`, `modeler`, `operator`, `viewer` — schützen jeden Endpunkt **zusätzlich** zur feingranularen BZR-Prüfung im Kern. Der **Modellierer** ist zugleich Bearbeiter: er erledigt Aufgaben über `GET /me/tasks`, führt Instanzen aus und darf **eigene Entwürfe als Test-Instanz** starten (ohne Audit-Events → aus den Monitoring-KPIs ausgeschlossen); `operator` startet/bearbeitet nur **freigegebene** Instanzen und liest das Monitoring; `viewer` ist rein lesend (kein Instanzstart). Eine angemeldete Person erreicht über `GET /me/tasks` direkt ihre eigene Arbeitsliste (`GET /auth/me` liefert die verifizierte Identität); die handelnde Identität für `complete`/`decide` stammt aus dem Token, nicht aus dem Request-Body (Impersonation-Schutz). CORS ist über `PROCWORKS_CORS_ORIGINS` härtbar. Details: [docs/Auth-Konzept.md](docs/Auth-Konzept.md).
- **Web-Client** ([web/](web/)): schlanker **No-Build**-Web-Client (reines HTML/CSS/JS, kein Bundler) als dünne GUI mit acht Sichten — Modellieren (geführte +-Operationen, live validiert; ausgewählte Knoten lassen sich umbenennen und entfernen, das Modell zentriert die Auswahl), Datensicht, Ressourcensicht (Organisation als **Baumstruktur** mit Abteilungen, Vorgesetzten und Umhängen-Dialog; Agenten samt Vertreter in eigener Tabelle; zusätzlich ein **Organigramm** der Abteilungs-Hierarchie, dessen Klick die gewählte Abteilung samt zugehöriger Agenten inkl. Vorgesetztem hervorhebt), Ausführung (Worklist + Live-Prozesslandkarte), Meine Aufgaben (Bearbeiter-Aufgabenliste), Monitoring, Integration (Connector-Registry, Datenanbindungs-Assistent, Automatik-Binding, Webhook-Panel, Inzident-Liste) und Hilfe (Kurzübersicht aller Sichten, Schnellstart je Rolle, Glossar der Regel-Codes). Die Kontrollflussansicht (Modellieren) und die Live-Prozesslandkarte (Ausführung/Monitoring) sind **frei verschiebbar** (Ziehen in alle Richtungen) und **per Mausrad zoombar** – immer zur aktuellen Zeigerposition hin bzw. von ihr weg. Jede Mutation läuft über den Validate-before-Commit-Pfad des Kerns; die GUI trägt **keine** Korrektheitslogik.
- **Persistenz**: austauschbarer Store für Schemata, Instanzen und das Event-Log — in-memory ohne Konfiguration, PostgreSQL via `DATABASE_URL` (SQLAlchemy 2.0, JSONB, Alembic-Migrationen `0001`/`0002`/`0003`/`0004`, docker-compose; `0004` legt die Registry geteilter Organisationsmodelle an); Instanzen und Audit-Verlauf sind durabel.
- **Ad-hoc-Änderungen (R1/R2)**: eine einzelne laufende Instanz wird über eine instanzeigene Schema-Variante (`ad_hoc_schema`) angepasst (`adhoc_insert_activity`/`adhoc_delete_node`); R1 schützt die noch nicht ausgeführte Region, R2 validiert die Variante vor dem Commit. Die Engine läuft nahtlos weiter.
- **Schema-Evolution + Instanzmigration (M1–M5)**: `new_revision` erzeugt eine ID-erhaltende Revision; `check_migration`/`migrate_instance` ziehen laufende Instanzen um, wenn die ausgeführte Region erhalten bleibt (M1 Ziel korrekt+RELEASED, M2 Region unverändert, M3 saubere Markierungsabbildung, M4 Pflichtdaten verfügbar, M5 ad-hoc Instanzen blockiert).
- **BPMN-Import/Export** (`bpmn.py`): Schemata werden als semantisches BPMN 2.0 exportiert (Events/`task`/`callActivity`/`parallelGateway`/`exclusiveGateway`, Bedingungen als `conditionExpression`) und auf der geprüften Block-Teilsprache zurückgelesen. Der Import validiert **vor** dem Speichern (No-Bypass): fehlerhaftes XML oder Konstrukte außerhalb der Teilsprache liefern `BpmnError`, nicht block-strukturierte Graphen werden über K1-K3 abgelehnt; der Split-/Join-Typ wird über den Knotengrad erschlossen (semantisches BPMN, kein Diagramm-Layout).
- **Monitoring/Audit + Process Mining** (`audit.py`): jede Laufzeitoperation wird **an der API-Grenze** in ein append-only Event-Log geschrieben (der Ausführungskern bleibt rein). Aus der Historie liefert die API eine **Audit-Timeline** je Instanz (`GET /instances/{id}/audit`), **KPIs** (`GET /monitoring/kpis`: laufend/abgeschlossen, Ø Durchlaufzeit, je Aktivität Abschlüsse + Ø Dauer als Engpass-Signal) und eine entdeckte **Prozesskarte** (`GET /monitoring/process-map`, Directly-follows-Graph als leichtes Process Mining). Der Web-Client zeigt das in der Monitoring-Sicht (KPI-Kacheln, Engpass-Tabelle, Prozesskarte, Audit-Verlauf je Instanz — der **Bearbeiter** steht dabei in einer eigenen Spalte).
- **Beispieldaten & Reset (nur Administrator)**: ein eingebauter Demo-Datensatz (`demo.py`) macht alle Funktionen sofort greifbar — eine geteilte Organisation, ein **freigegebener** Prozess „Urlaubsantrag" und ein **Entwurf** „Beschaffung", dazu **drei Instanzen** an unterschiedlichen Punkten (eine frisch gestartet, eine in der Genehmigung, eine abgeschlossen) inklusive Audit-Verlauf und KPIs. Über `POST /admin/reset` setzt **ausschließlich** die Rolle `admin` das System **auf Null** zurück (Schemata, Instanzen, Organisationsmodelle, im Login-Betrieb auch alle Nutzer) und lädt die Beispieldaten optional wieder (`{"load_demo": true}`). Die handelnde Administrator-Identität und das Bootstrap-Konto `admin` bleiben dabei erhalten (kein Aussperren). Im Web-Client steht das als Bereich **„Wartung (Administrator)"** in der Monitoring-Sicht; die Testbenutzer-Logins sind im Schnellstart dokumentiert.
- **Modellanalyse, Priorität & Zeit (additiv, konzeptgetrieben)**: lesende **Modellmetriken & 7PMG-Hinweise** (`metrics.py`, `GET /schemas/{id}/metrics`: Größe, Verschachtelungstiefe, Gateway-Heterogenität, Konnektorgrad — nicht-blockierend, ohne Einfluss auf die Korrektheit), optionale **Wertschöpfungs-Klassifikation** je Knoten (`set_value_class`), **Arbeitslisten-Priorität** = Auswirkung + Dringlichkeit mit Sortierung der offenen Aufgaben (`set_node_priority`, `OpenTask.priority`) und eine statische **Zeitperspektive T1/T2** (Dauer-/Fristfelder; der kritische Pfad muss die Frist einhalten — als eigene, nur bei vorhandenen Zeitangaben greifende Validierungsgruppe, `set_time_constraint`/`set_deadline`). Die KPI-Auswertung trägt zusätzlich eine **Flexibilitäts-Kennzahl** (Ad-hoc-Anteil); Kosten/Qualität bleiben bewusst offen.
- **Deployment** (`core/Dockerfile`, `web/Dockerfile`, [deploy/](deploy/)): zustandsloses API-Container-Image (Migrationen beim Start, dann Uvicorn, non-root) plus Web/SPA hinter **Caddy** als Reverse Proxy mit automatischem TLS (Let's Encrypt), das `/api/*` an die API routet. Voller lokaler Stack via [deploy/docker-compose.full.yml](deploy/docker-compose.full.yml) (PostgreSQL + API + Web), Produktion via **Helm-Chart** ([deploy/helm/](deploy/helm/)). Der gebündelte Produktions-Stack (Compose/Helm) aktiviert standardmäßig das **Passwort-Login** (`PROCWORKS_AUTH=password`); beim ersten Start eines leeren Stores wird automatisch ein `admin`-Konto mit zufälligem Einmal-Passwort angelegt und ins API-Log geschrieben (erzwungener Wechsel beim ersten Login). **CI/CD**: GitHub Actions baut beide Images, scannt sie mit **Trivy** und veröffentlicht sie bei einem Versions-Tag nach **ghcr.io**. Erstinstallation auf einem Windows Server: [docs/Windows-Server-Setup.md](docs/Windows-Server-Setup.md). Anleitung für Mitarbeiter (Anmelden + Aufgaben bearbeiten): [docs/Mitarbeiter-Anleitung.md](docs/Mitarbeiter-Anleitung.md).
- 604 Tests (pytest), `ruff` + `mypy --strict` grün.

```powershell
cd core
..\.venv\Scripts\python.exe -m pip install -e ".[dev]"
..\.venv\Scripts\python.exe -m pytest -q
```

Details: [core/README.md](core/README.md).

## Projektstruktur

```text
.
- core/        # Headless Backend-Kern (Python/FastAPI, Walking Skeleton)
- web/         # Schlanker No-Build-Web-Client (HTML/CSS/JS, acht Sichten)
- deploy/      # Caddyfile, Full-Stack docker-compose, Helm-Chart
- docs/        # Architektur-Konzept, Quellen-Extrakte
- prototype/   # Klickbarer UI-Prototyp (HTML/CSS/JS, kein Build)
- tools/       # Hilfsskripte (z. B. PDF-Extraktion)
- .github/     # CI-Workflows (CI + Container-Release), Dependabot
```

Die Ziel-Architektur (Monorepo mit `apps/`, `packages/`, `services/`,
`deploy/`) ist im Konzept beschrieben, Abschnitt 10.

## Technologie (geplant, Open Source)

- **Frontend:** TypeScript-SPA (React) + `bpmn-js` als Editor/Viewer
  (nicht die Korrektheits-Instanz – diese liegt im geprüften Kern).
- **Backend/Kern:** **Python 3.12+ / FastAPI / Pydantic** (siehe [core/](core/));
  korrektheitserhaltende Operationskontrakte; Validatoren für
  K/D/Z/B/R/M-Regeln.
- **Daten:** PostgreSQL (primär); optional Redis, OpenSearch.
- **Konnektoren:** MS SQL Server, MySQL, MS Dynamics 365 (Dataverse/OData),
  SAP (OData/Gateway/BAPI/RFC) über eine Data-Access-Layer-SPI.
- **Betrieb:** Docker / docker-compose / Kubernetes (+Helm), Traefik/Caddy (TLS),
  Keycloak (OIDC), OpenTelemetry/Prometheus/Grafana, Images via `ghcr.io`.

## Roadmap

Siehe Umsetzungs-Roadmap im Konzept
([docs/Architektur-Konzept-Prozessmodellierung.md](docs/Architektur-Konzept-Prozessmodellierung.md),
Abschnitt 13). Aktueller Stand: **Konzept + klickbarer Prototyp + Backend-Kern (Walking Skeleton)**.

## Mitwirken

Beiträge sind willkommen. Bitte vor größeren Änderungen ein Issue eröffnen, damit
Richtung und Konsistenz (insbesondere die Korrektheitsinvariante) abgestimmt sind.
Die CI prüft Markdown und die Prototyp-Dateien automatisch (siehe
[.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Herkunft & Originalität

ProcWorks ist eine **eigenständige, von Grund auf neu geschriebene**
Implementierung. Es übernimmt aus der Forschung **nur Konzepte**, keinen Code:

- **Kein Fremdcode eingebettet.** Es ist keine externe Bibliothek in dieses
  Repository kopiert; Web-Client und Prototyp laden ausschließlich **lokale**
  Erstanbieter-Dateien (kein CDN, keine gebündelten Fonts, keine fremden
  Minified-Bundles). Abhängigkeiten werden separat von PyPI bezogen und
  **unverändert** über ihre öffentlichen Schnittstellen genutzt.
- **ADEPT2 / BPMN nur konzeptionell.** Die Korrektheitsideen (Blockstruktur,
  K/D/Z/B-Kriterien, High-Level-Operationen, Markierungssemantik, Migration)
  stammen aus **veröffentlichter Forschung** (ADEPT2, Universität Ulm) und dem
  **offenen OMG-Standard BPMN 2.0** und sind in eigenem Python neu umgesetzt.
  **Kein ADEPT-Quellcode** wird verwendet, kopiert oder abgeleitet.
  Die akademischen Quellen sind in
  [docs/Architektur-Konzept-Prozessmodellierung.md](docs/Architektur-Konzept-Prozessmodellierung.md)
  (§15) belegt. „ADEPT" wird ausschließlich **nennend/
  beschreibend** zur Würdigung der zugrunde liegenden Forschung verwendet; es
  besteht **keine** Verbindung, Partnerschaft oder Billigung durch deren Inhaber.
- **Geschütztes Quellmaterial bleibt draußen.** Forschungs-PDFs und daraus
  extrahierte Volltexte werden nie eingecheckt (per `.gitignore` ausgeschlossen).
- **Drittlizenzen dokumentiert.** Alle Abhängigkeiten und ihre Lizenzen sind in
  [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) aufgeführt.

## Lizenz

Veröffentlicht unter der **Business Source License 1.1 (BUSL-1.1)** –
quelloffen und **kostenlos zum Testen, Entwickeln und für nicht-konkurrierende
Produktivnutzung**, **ohne jegliche Gewährleistung oder Haftung**. Eine
**konkurrierende kommerzielle Nutzung** (insbesondere das Anbieten als
gehosteter/eingebetteter Dienst im Wettbewerb zum Lizenzgeber oder der
Weiterverkauf als kommerzielles Prozessmanagement-Produkt) erfordert eine
**kommerzielle Lizenz** des Lizenzgebers. Am **Change Date (2030-06-17)** geht
jede betroffene Version automatisch in **Apache-2.0** über. Siehe
[LICENSE](LICENSE).

Für kommerzielle Lizenzen wende dich an den Lizenzgeber.

### Haftungsausschluss

ProcWorks wird **„wie besehen" (as is)**, **ohne jede Gewährleistung** und
**ohne jede Haftung** bereitgestellt. Bezug, Installation, Inbetriebnahme und
Nutzung erfolgen **ausschließlich auf eigenes Risiko und in eigener
Verantwortung**. Im größtmöglichen gesetzlich zulässigen Umfang übernehmen wir
**keine Haftung für irgendeinen Schaden** – weder im Zusammenhang mit der
**Inbetriebnahme** (z. B. Schäden an Servern, Hardware, Betriebssystemen,
paralleler oder Drittsoftware, Netzwerken oder sonstiger Infrastruktur) noch mit
der **Nutzung** (z. B. Verlust, Beschädigung oder Offenlegung von Daten,
fehlerhafte, verzögerte oder unterbrochene Geschäftsprozesse, Betriebs- oder
Vermögensschäden). Dies ergänzt den Gewährleistungs-/Haftungsausschluss der
Lizenz (BUSL-1.1, Abschnitt 8). Zwingende gesetzliche Haftung (insbesondere bei
Vorsatz, grober Fahrlässigkeit, Verletzung von Leben/Körper/Gesundheit sowie nach
dem Produkthaftungsgesetz) bleibt unberührt. Vollständiger Text:
[DISCLAIMER.md](DISCLAIMER.md).

© 2026 Tobias Häcker – alle Rechte vorbehalten.
