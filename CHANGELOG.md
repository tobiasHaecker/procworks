# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei
dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
- **Wiederverwendbare Subprozesse mit Submodell-Bibliothek und
  Datenübergabe:** Eine Aktivität lässt sich jetzt in einen **Subprozess
  umwandeln**, der an ein eigenständig entwickeltes, freigegebenes **Submodell**
  bindet. Freigegebene Modelle können per Kopf-Schalter „Als Submodell" in eine
  **Bibliothek** aufgenommen werden (`GET /subprocess-library`) und stehen dann
  in anderen Modellen zur Wiederverwendung bereit. Beim Zuweisen gilt
  **Correctness by Construction**: die Verbindung wird nur gesetzt, wenn das
  resultierende Gesamtmodell konsistent und lauffähig bleibt – der Kern erzwingt
  H1–H4 (gültige Bindung, freigegebenes Ziel, typkonforme Zuordnung, azyklische
  Hierarchie) samt vollständiger Validierung, andernfalls wird die Umwandlung
  mit HTTP 422 abgelehnt. Die **Datenübergabe** ist Teil der Korrektheit: die
  Ergebnis-Zuordnung eines Subprozesses zählt jetzt als garantierte Schreibung
  im Datenfluss (D1/D2), und eine Ausgabe darf nur gemappt werden, wenn das
  Submodell sie auf **jedem** Pfad erzeugt (sonst H2). Neue Kern-Operationen
  `convert_activity_to_subprocess`, `set_subprocess_binding` und
  `set_library_subprocess`; neues additives Feld
  `ProcessSchema.is_library_subprocess`; neue Endpunkte
  `POST /schemas/{id}/convert-to-subprocess`,
  `POST /schemas/{id}/subprocess-binding`, `POST /schemas/{id}/library-flag` und
  `GET /subprocess-library`. Im Knoten-Inspektor des Modellierers: „In Subprozess
  umwandeln" (Aktivität) bzw. „Zuordnung / Datenübergabe ändern" (Subprozess)
  mit geführtem Zuordnungsdialog (nur typgleiche Elternelemente werden
  angeboten). Tests ergänzt (Kern und API).

- **Popup-Hinweis bei neu eintreffenden Aufgaben:** Ist die Aufgabenliste eines
  Agenten geöffnet und trifft während der Live-Aktualisierung eine neue Aufgabe
  ein, erscheint ein kurzer, sich selbst schließender Hinweis (Toast). Bei einer
  einzelnen neuen Aufgabe „Neue Aufgabe eingetroffen", bei mehreren die Anzahl
  samt der ersten betroffenen Aufgaben. Der Hinweis verschwindet nach wenigen
  Sekunden von selbst.

- **Ad-hoc-Anpassung einer einzelnen Instanz im Ausführungsmodul:** Der
  Modellierer kann eine **laufende Instanz** an die Realität anpassen, ohne das
  freigegebene Schema zu ändern – kein Modell ist so statisch, dass bei
  Abweichungen am Prozess vorbei gearbeitet werden muss. Im Ausführungs-Detail
  einer Instanz gibt es ein Panel „Instanz anpassen (Ad-hoc)" (Rollen
  `modeler`/`admin`, nur bei laufender Instanz) mit den Aktionen **Schritt
  einfügen**, **Schritt umbenennen** und **Schritt entfernen**. Die UI bietet
  vorab nur zulässige Ziele im noch nicht ausgeführten Bereich an; der Kern
  erzwingt weiterhin **R1** (Zustandskompatibilität – bereits erreichte Schritte
  sind eingefroren) und **R2** (Korrektheitserhalt – Prüfung der Instanz-Variante
  vor Übernahme). Neue Kern-Operation `adhoc_rename_activity` (rein
  strukturneutrale Umbenennung eines noch nicht erreichten `ACTIVITY`/
  `SUBPROCESS`-Knotens), neuer Endpunkt
  `POST /instances/{id}/adhoc/rename` und neues Audit-Ereignis `ADHOC_RENAMED`
  (fließt in die Ad-hoc-Zählung der Prozesslandkarte ein). Die bereits
  vorhandenen Operationen `adhoc_insert_activity`/`adhoc_delete_node` sind damit
  erstmals über die Weboberfläche erreichbar; angewendete Anpassungen werden aus
  `ad_hoc_deltas` protokolliert angezeigt. Tests ergänzt (Kern und API).

- **Eingabemasken-Designer im Modellierungsmodul:** Für jede Aktivität lässt
  sich jetzt per Auswahl eine **Eingabemaske** gestalten – Textfelder,
  Textbereiche, Zahlenfelder, Auswahllisten (Dropdown), Kontrollkästchen und
  Datumsfelder werden aus den Datenelementen zusammengestellt. Die **Anordnung
  entsteht automatisch** (geordnete Feldliste → Raster, inkl. Live-Vorschau);
  es sind keine Koordinaten im Modell nötig. Jedes Feld wird an ein Datenelement
  gebunden und ist eine Präsentationsschicht über einem Datenzugriff, sodass
  **Correctness by Construction** auch für Masken gilt: Ein Anzeigefeld (READ)
  erzeugt einen Lesezugriff, den der Kern über **D1** ablehnt, wenn das Element
  nicht auf **jedem** Pfad zuvor gesetzt wurde („kein Read ohne Set") – gerade
  auch bei komplex verzweigten Modellen. Neue Meta-Modell-Typen `Form`,
  `FormField`, `WidgetKind` und `ProcessSchema.forms`; neue Operationen
  `set_form`/`delete_form`; neue Validierungsregeln **U1–U3** (Wohlgeformtheit
  der Maske und Konsistenz von Maske ↔ Datenfluss); neue Endpunkte
  `POST`/`DELETE /schemas/{id}/nodes/{node_id}/form` (Rollen `modeler`/`admin`).
  Die Maske wird im BPMN-Export über die `procworks:model`-Erweiterung
  verlustfrei mitgeführt. Zur Laufzeit rendert der Web-Client den Abschluss-
  dialog eines Schritts aus der gestalteten Maske (Dropdowns, Kontrollkästchen
  usw.); Anzeigefelder bleiben schreibgeschützt. Umfangreiche Tests ergänzt.
- **Instanzdaten direkt nach dem Start eingeben:** Direkt nach dem Aktivieren
  einer Instanz lassen sich jetzt Datenwerte eingeben, **ohne zuvor die erste
  Aktivität abschließen zu müssen**. Neuer Endpunkt `PUT /instances/{id}/data`
  (Rollen `operator`/`modeler`/`admin`) setzt Prozessvariablen direkt auf einer
  Instanz, typgeprüft gegen das Schema (D3; unbekannte Elemente oder Typfehler →
  HTTP 422) und ohne Audit-Ereignis (keine KPI-Verschmutzung). Im Web-Client
  bietet die Ausführungssicht dazu im Bereich **„Instanzdaten"** die Schaltfläche
  **„Daten eingeben"**, die alle `INSTANCE`-Datenelemente des Schemas mit ihren
  aktuellen Werten zur Eingabe anbietet (`EXTERNAL`-Elemente bleiben ausgenommen,
  da sie zur Laufzeit über Connectoren aufgelöst werden). Regressionstests
  ergänzt.

### Behoben
- **Test-Instanzen verschmutzen das Monitoring nicht mehr über ihren gesamten
  Lebenszyklus:** Eine als `is_test` markierte Test-Instanz eines Entwurfs war
  bisher nur *beim Start* von Audit-Log und KPIs ausgenommen – das Abschließen
  von Schritten (`/complete`), das Starten von Schritten (`/start`) sowie
  Ad-hoc-Änderungen schrieben dennoch `ACTIVITY_STARTED`/`ACTIVITY_COMPLETED`/
  `INSTANCE_COMPLETED`/`ADHOC_*`-Ereignisse in das globale Audit-Log und lösten
  Webhooks/HTTP-Pushes aus. Damit sickerten Testdaten in die produktiven KPIs
  und die Prozesslandkarte. Jetzt bleibt eine Test-Instanz über ihren **ganzen
  Lebenszyklus** frei von Audit-Ereignissen, KPIs und externen Nebenwirkungen
  (wie im Docstring von `POST /schemas/{id}/instances` zugesichert). Regressions-
  test ergänzt.

### Geändert
- **Seitliches Scrollen in der Modellansicht:** In der Kontrollfluss-Canvas
  (Modellierung, Ausführung, Monitoring) verschiebt das Mausrad bzw. die
  Trackpad-Wischgeste die Ansicht jetzt frei in beide Richtungen; horizontales
  Wischen (oder Umschalt+Rad) scrollt seitlich, `Strg`/Pinch zoomt weiterhin
  zum Zeiger. Der Canvas-Hinweistext wurde entsprechend angepasst.

- **XOR-Verzweigungen sind jetzt „Correctness by Construction" (K7
  konstruktiv erzwungen):** Ein XOR-Split trägt keine frei formulierbaren
  Bedingungen mehr, sondern eine **strukturierte, entscheidbare Partition** über
  genau einem typisierten **Diskriminator-Datenelement**. Drei Formen werden
  unterstützt – **THRESHOLD** (INTEGER/FLOAT, strikt aufsteigende Obergrenzen,
  letzter Zweig offen), **BOOLEAN** (genau zwei Zweige true/false) und **ENUM**
  (STRING, disjunkte Wertelisten plus genau ein *otherwise*-Zweig). Damit ist
  jede Verzweigung per Konstruktion **vollständig** (es trifft immer genau ein
  Zweig) und **überlappungsfrei** (nie können mehrere Pfade aktiviert werden);
  inkonsistente, lückenhafte oder OR-artige Bedingungen sind **nicht
  modellierbar**. Der Diskriminator muss auf allen Pfaden vor dem Split
  geschrieben sein, sodass weder Deadlock noch Livelock entstehen kann. Die
  Eigenschaft ist Teil der Korrektheitsinvariante I und bleibt über die gesamte
  **Modell-Evolution** (neue Revision, Instanzmigration, Ad-hoc-Änderung)
  erhalten.
  - Die Ausführungs-Engine **wählt den Zweig automatisch** aus den Instanzdaten
    aus; der frühere manuelle Entscheidungsschritt (`/instances/{id}/decide`,
    „Zweig wählen") entfällt ersatzlos.
  - `conditional-insert` (API/Web/Kern-Operation) erwartet jetzt einen
    `discriminator` und eine `branches`-Partition statt freier Bedingungstexte.
  - BPMN-Export/-Import transportieren die Datenebene (Datenelemente,
    Datenzugriffe, XOR-Partition) verlustfrei über eine prozessweite
    `procworks:model`-Erweiterung, damit K7-Modelle round-trip-fähig bleiben.

### Hinzugefügt
- **Prüfinstanz – 4-Quadranten-Analyse-Cockpit für Entwürfe** (Web-Client,
  rein additiv, keine Kernänderung): Modellierer/Administratoren können einen
  **noch nicht freigegebenen Entwurf** als **Test-Instanz durchspielen**, um das
  Modellkonzept zu erarbeiten. Der Start erfolgt aus der Modellieransicht
  (Kopf-Button „⚗ Prüfinstanz") oder über den neuen Navigationseintrag; ein
  Dialog fragt zunächst, **wer die Instanz startet**. Die Analyse-Sicht ist in
  vier Quadranten geteilt: **oben links** ein auf genau diese Instanz
  beschränktes **Monitoring** (Live-Prozesslandkarte, Fortschritt, Instanzdaten,
  Schrittübersicht mit Status und Bearbeiter je Schritt), **oben rechts** der
  **angemeldete Starter** (Identitätskarte mit Rollen/Abteilung) und **unten**
  zwei **frei wählbare, umschaltbare beteiligte Agenten**, deren **Arbeitsliste
  jeweils auf diese laufende Instanz gefiltert** ist. Aufgaben lassen sich pro
  Agent direkt erledigen, sodass der Ablauf Schritt für Schritt nachgespielt
  werden kann. Die Sicht trägt – wie der
  gesamte Client – **keine Korrektheitslogik**; die instanzgefilterte
  Arbeitsliste entsteht rein clientseitig aus `GET /instances/{id}/tasks`, alle
  Abschlüsse laufen über den geprüften `/complete`-Endpunkt.
- **Organigramm & Abteilungs-/Agenten-Hervorhebung in der Ressourcensicht**
  (Web-Client, rein additiv): Rechts unter „Ressourcen-Befunde" zeigt ein
  **Organigramm** die modellierte Organisation (Abteilungs-Hierarchie mit
  Vorgesetztem und Agenten-Anzahl je Einheit) als klassisches Org-Chart.
  - **Klick auf eine Abteilung** (im Organigramm) hebt die gewählte Abteilung
    – im Organigramm und im Abteilungsbaum – hervor und markiert **alle zu ihr
    gehörenden Agenten inkl. Vorgesetztem** in der Agentenliste; ein
    schließbares Hinweis-Banner erklärt die Hervorhebung.
  - **Klick auf den Vorgesetzten** (★-Badge im Bereich „Abteilungen") hebt
    diesen Vorgesetzten gezielt in der Agentenliste hervor.
  - Reine Anzeige-/Navigationshilfe im Client; keine Backend- oder
    Modelländerung.
- **Audit-Verlauf: Bearbeiter in eigener Spalte** (Web-Client): Der
  Audit-Verlauf einer Instanz stellt den **Bearbeiter (Akteur)** jetzt in einer
  eigenen Spalte dar (mit Spaltenkopf „Zeit / Ereignis / Bearbeiter / Detail");
  Ereignisse ohne handelnden Agenten werden als „System" ausgewiesen. Die Daten
  stammen unverändert aus dem `agent_id`-Feld der Audit-Ereignisse.
- **Nutzerhilfe & Dokumentation ausgebaut**:
  - **In-App-Hilfe** (Web-Client, neue Sicht **„Hilfe"**, für alle Rollen
    sichtbar): Kurzübersicht aller Sichten, Schnellstart je Rolle mit Deep-Links
    zu den Anleitungen und ein **Glossar aller Regel-Codes** (K/D/C/Z/A/I/H/F/T/B/M/R/G),
    die in der Befunde-Liste und in Fehlermeldungen erscheinen. Rein im Client,
    keine Backend-Änderung.
  - **[docs/Modellierer-Anleitung.md](docs/Modellierer-Anleitung.md)** (neu):
    Schritt-für-Schritt vom neuen Schema über Schritte/Daten/Bearbeiter und
    Testlauf bis zur Freigabe und Revision.
  - **[docs/README.md](docs/README.md)** (neu): Dokumentations-Übersicht, die
    nach Rolle (Modellierer / Sachbearbeiter / Administrator / Integrator) führt
    und alle weiteren Dokumente listet.
- **Verknüpfte Datenelemente & Bearbeiterzuordnung in der Kontrollflussansicht**
  (Web-Client, rein additiv): Jeder Aktivitäts-/Teilprozess-Knoten zeigt jetzt
  am unteren Rand kompakte Badges für seine **Datenbindungen** („Daten N“, mit
  Tooltip der Elementnamen und Zugriffsmodi) und seine **Bearbeiterregel**
  („Bearbeiter“, Tooltip mit der Regel).
  - **Sprung in die jeweilige Ansicht**: Ein Klick auf das Daten-Badge öffnet die
    **Datensicht**, ein Klick auf das Bearbeiter-Badge die **Ressourcensicht**
    (Bearbeiterzuordnung); in der Live-Prozesslandkarte sind die Badges
    informativ (ohne Sprung).
  - **Hervorhebung des selektierten Schritts**: Die Zielansicht hebt die
    zugehörige Zeile farbig hervor, scrollt sie in den Sichtbereich und zeigt
ein schließbares Hinweis-Banner („Hervorhebung löschen“). Ein Wechsel über
    die Navigation setzt die Hervorhebung zurück.

### Geändert
- **Monitoring-Ansicht neu sortiert** (Web-Client): Die **Live-Prozesslandkarte**
  der ausgewählten Instanz wird jetzt direkt unter „Aktive Instanzen“
  dargestellt; der Block **Wartung (Administrator)** rückt ganz nach unten, da
  er selten benötigt wird und destruktive Aktionen enthält.

### Hinzugefügt
- **Integrationsschicht Phase P6 – HTTP-Push für Aktivitäten & Integrations-Dokumentation (Konzept §6.3)**:
  Die **Push-Seite** der ausgehenden Anbindung – ProcWorks ruft bei Aktivierung
  einer automatischen Aktivität aktiv ein konfiguriertes Tool-Endpoint auf
  (komplementär zum bestehenden External-Task-*Pull*).
  - **Push-Endpoint-Registry** (`outbox.py`): `PushEndpointRegistry` löst eine
    logische `endpoint_ref` aus dem Service-Binding serverseitig zu URL +
    Signatur-Secret auf (`build_push_endpoint_registry()` liest
    `PROCWORKS_PUSH_ENDPOINTS`, Dateipfad oder Inline-JSON). URLs und Secrets
    stehen **nie** im Schema; `GET /v1/push-endpoints` listet nur die Referenzen.
  - **Subskriptionslose Outbox-Zustellung** (`OutboxDispatcher.push`): nutzt die
    volle Outbox-Maschinerie (durable Queue, HMAC-Signatur, Back-off-Retry,
    Circuit-Breaker, Delivery-Log) für vertrauenswürdige, vom Betreiber
    konfigurierte Ziele (SSRF-Prüfung auf Schema + Host, interne Hosts erlaubt).
    Additives Modellfeld `OutboxEntry.secret_ref`.
  - **Push-Treiber** (`ExternalTaskRuntime.drive_push`): materialisiert je
    aktiviertem `HTTP_PUSH`-Schritt eine Aufgabe und pusht ihr Eingabe-Datenpaket
    inklusive **Callback-Token** an das Ziel. Die Aufgabe wird `LOCKED` (ohne
    Lock-Ablauf, ohne Topic) – das Tool quittiert und meldet das Ergebnis später
    über den **regulären** `POST /v1/external-tasks/{id}/complete`-Endpunkt
    zurück (asynchrone Variante; die synchrone Variante bleibt bewusst
    aufgeschoben, weil sie den Kern an die Zustellung koppeln würde).
  - **Best-Effort & stabil**: der Push wird nach jedem Engine-Fortschritt
    angestoßen, schlägt er fehl, bleibt die Aufgabe `CREATED` und wird später
    erneut gepusht – der Prozess wird **nie** blockiert oder beschädigt.
    `POST /v1/external-tasks/drive-push` stößt einen Drive manuell an
    (z. B. Re-Push nach Backoff; operator/admin).
  - **Dokumentation**: neuer [Integrations-Leitfaden](docs/Integrations-Leitfaden.md)
    (Rezepte für Inbound, External-Task-Pull, HTTP-Push, Webhooks, Connectoren,
    Auth/Scopes, Idempotenz + Endpunkt-Referenz); OpenAPI unter `/docs`.
  - Rein additiv, Boundary-only; der Kern bleibt rein. 467 Tests grün
    (+22 neue in `tests/test_http_push.py`).
- **Integrationsschicht Phase P5 – GUI-Integrationssicht (Konzept §11)**:
  Neue **Integrations-Sicht** im No-Build-Web-Client (`web/`), die ausschließlich
  geprüfte Endpunkte aufruft (keine Korrektheitslogik im Client).
  - **Connector-Registry** (§11.1): Liste der serverseitig konfigurierten
    Connectoren mit Typ-Badge und Status (verbunden/Fehler/ungeprüft),
    „Verbindung testen" (`/v1/connectors/{id}/test`) und „Testlesen"
    (`/v1/connectors/{id}/sample-read`). Zugangsdaten werden nie angezeigt.
  - **Datenanbindungs-Assistent** (§11.2): Modell-Connectoren registrieren und
    Datenelemente extern an Connector-Entitäten binden (Schlüssel-Datenelement),
    live gegen die Connector-Regeln C1–C3 geprüft.
  - **Automatik-Schritt-Binding** (§11.3): Umschalter „Person / Automatisch"
    pro Aktivität (External-Task-Topic oder HTTP-Push-Ziel) samt einklappbarer
    Robustheits-Parameter (Versuche/Backoff/Timeout) über `…/automation`.
  - **Webhook-/Ereignis-Panel** (§11.4): Abonnements anlegen (URL gegen
    Allowlist, Ereignisse als Checkboxen, Secret-Referenz), „Testzustellung"
    und Zustellprotokoll einsehen, Abonnement löschen.
  - **Inzident-Liste** (§11.5) in der Monitoring-Sicht: offene Inzidente
    externer Aufgaben mit „Erneut versuchen" (Auflösen + Wiedereinreihen) für
    Bearbeiter/Administratoren.
  - Rein additiv, nur Web-Client (`app.js`/`index.html`/`styles.css`); der Kern
    und die API bleiben unverändert (445 Tests weiterhin grün).
- **Integrationsschicht Phase P4 – Webhooks & transaktionaler Outbox (E13, Konzept §6.3)**:
  Die **Event-Seite** der maximal offenen API – Fremd-Tools abonnieren
  Domänen-Ereignisse und erhalten sie als signierte HTTP-POSTs.
  - **Transaktionaler Outbox-Dispatcher** (`outbox.py`, neu): `OutboxDispatcher`
    reiht ein Ereignis je aktivem, passendem Abo in den **Outbox** ein (vor der
    Zustellung persistiert – kein Verlust bei Absturz) und stellt es danach zu.
    Eigenschaften: **At-least-once + Idempotenz** (eindeutige `delivery_id` je
    Zustellung), **HMAC-SHA256-Signatur** (`X-ProcWorks-Signature`, Secret aus
    dem serverseitigen Secret-Store – nie inline), **Back-off-Retry** mit
    Dead-Letter (`OutboxEntry`-Zustand `DEAD` nach erschöpftem Budget),
    **Circuit-Breaker** je Ziel-Host und **Delivery-Log** (`WebhookDelivery`).
  - **SSRF-Allowlist (Regel I6)**: eine Abo-URL wird vor Speichern und Aufruf
    geprüft – nur `http`/`https`, Host gegen `PROCWORKS_WEBHOOK_ALLOWLIST` bzw.
    Sperre interner/loopback/link-local-Adressen ohne Allowlist.
  - **Event-Quelle**: der External-Task-Treiber meldet `task.ready` /
    `task.completed` / `task.incident` über eine optionale Boundary-Senke; die
    API emittiert `instance.started` / `instance.completed`. Der Kern bleibt
    rein (die Senke speist nie in die Engine zurück).
  - **Persistenz**: `WebhookStore` (Protocol) mit `InMemoryWebhookStore` und
    `SqlAlchemyWebhookStore` (Dokument-Zeilen-Muster), Migration
    `0007_webhook_outbox` (Abo-, Outbox- und Delivery-Tabellen).
  - **Endpunkte** (`/v1/webhooks`): `GET`/`POST /v1/webhooks`,
    `DELETE …/{id}`, `POST …/{id}/test` (synthetischer Ping), `GET …/{id}/deliveries`
    (Delivery-Log), abgesichert über `events:subscribe` (modeler/admin).
  - Rein additiv, Boundary-only; der Kern bleibt rein. Alle bestehenden Tests
    bleiben grün (445 Tests, +27 neue in `tests/test_webhooks_outbox.py`).
- **Integrationsschicht Phase P3 – Daten-Connectoren (R4/R5, Konzept §7)**:
  Reale, parametrisierte Datenanbindung an Fachsysteme über die bestehende
  DAL-SPI.
  - **`SqlAlchemyConnector`** (`dal.py`): realer SQL-Connector über SQLAlchemy
    Core für jeden unterstützten Dialekt (PostgreSQL, MySQL/MariaDB, MS SQL,
    SQLite, …). Schlüssel und Werte reisen ausschließlich als **Bind-Parameter**;
    Tabellen-/Spalten-**Bezeichner** werden gegen ein striktes Muster
    whitelisted und dialekt-gequotet – keine Injektionsfläche.
  - **Connection-Registry & Secret-Store** (`connections.py`, neu):
    `ConnectionRegistry` bildet `connector_id` → technische Verbindung
    (`ConnectionConfig`) ab und baut Connectoren **lazy**. Secrets bleiben als
    `${ENV}`-Referenzen in der URL und werden erst zur Verbindungszeit aus der
    Umgebung aufgelöst (nie im Schema/VCS). `build_connection_registry()` liest
    `PROCWORKS_CONNECTIONS` (JSON-Datei oder Inline-JSON).
  - **Bidirektionaler Datenfluss** (`integration_runtime.py`): der
    External-Task-Treiber führt jetzt **Pre-Fetch** (READ auf `EXTERNAL`-Element
    → Datensatz beim Lock ins Eingabepaket) und **Post-Flush** (WRITE auf
    `EXTERNAL`-Element → vor dem Engine-Fortschritt zum Connector geschrieben)
    aus. Connector-Fehler erscheinen als `502`, ohne den Schritt voranzutreiben.
  - **Endpunkte** (`/v1/connectors`): `GET /v1/connectors` (Metadaten, nie
    Secrets), `POST …/{id}/test` (read-only Ping), `POST …/{id}/sample-read`
    (Beispieldatensätze für die GUI-Mapping-Hilfe), abgesichert über `data:read`.
  - Rein additiv, Boundary-only; der Kern bleibt rein. Alle bestehenden Tests
    bleiben grün (418 Tests, +21 neue in `tests/test_connectors_sql.py`).
    OData/Dynamics-365 bleibt als Folge-Connector offen (SPI unverändert).
- **Integrationsschicht Phase P2 – External-Task-Runtime / Outbound-Pull (E11)**:
  Automatische Aktivitäten werden als von Fremd-Workern abholbare Arbeitsschlange
  bereitgestellt, gemäß
  [docs/Integrations-Konzept-Externe-Anbindung.md](docs/Integrations-Konzept-Externe-Anbindung.md) §6.
  - **Runtime-Treiber** (`integration_runtime.py`, neu): `ExternalTaskRuntime`
    materialisiert Tasks **lazy** beim Fetch-and-lock-Scan (für aktivierte
    automatische `EXTERNAL_TASK`-Schritte ohne offenen Task), löst das
    Eingabe-Datenpaket aus `parameter_mapping`/READ-Zugriffen auf, schreibt
    Ausgaben über `parameter_mapping`/WRITE-Zugriffe und ruft den **reinen**
    Kern (`complete_activity`) – der Kern bleibt unangetastet.
  - **Robustheit**: Worker-gebundenes Lock mit Sichtbarkeitsfenster, automatische
    Rückgewinnung abgelaufener Locks, **exactly-once**-Abschluss über die
    Zustandsmaschine (ein doppelter Abschluss wird abgewiesen), Retry mit
    exponentiellem Back-off, Dead-Letter als `INCIDENT` bei erschöpften Retries,
    Prioritäts-Sortierung der Schlange.
  - **Endpunkte** (`/v1/external-tasks`): `POST …/fetch-and-lock`,
    `POST …/{taskId}/complete`, `…/failure`, `…/bpmn-error`, `…/extend-lock`,
    `…/unlock`, `GET …/{taskId}`, plus `GET /v1/incidents` und
    `POST /v1/incidents/{id}/resolve`. Fetch ist über `tasks:fetch`, alle
    schreibenden Aktionen über `tasks:complete` abgesichert.
  - **Modellierung**: Neuer Endpunkt `POST /schemas/{id}/automation`
    (`set_automation`) zum Konfigurieren von Topic/Retry der Automatik-Bindung.
  - **Persistenz**: `ExternalTaskStore` (in-memory + SQLAlchemy `external_task`/
    `incident`-Tabellen), Migration `0006_external_task`. Additive
    `ExternalTask`-Felder `available_at`/`error_code`; gemeinsamer Typprüfer
    `value_matches_type` (Modell) für Inbound-Daten und Task-Ausgaben.
  - Rein additiv, Boundary-only; der Kern bleibt rein. Alle bestehenden Tests
    bleiben grün (397 Tests, +15 neue in `tests/test_external_tasks.py`).
- **Integrationsschicht Phase P1 – Inbound-API-Härtung (E10)**: Versionierte,
  maximal offene Eintrittstür für Fremd-Tools gemäß
  [docs/Integrations-Konzept-Externe-Anbindung.md](docs/Integrations-Konzept-Externe-Anbindung.md) §5.
  - **Service-Identität & Scopes**: Neue Maschinen-Rolle `integration` neben den
    Personen-Rollen sowie feingranulare Scopes (`instances:start`,
    `tasks:complete`, `tasks:fetch`, `data:read`, `data:write`,
    `events:subscribe`, Wildcard `*`). Service-Token tragen ihre Scopes im
    `PROCWORKS_TOKENS`-JSON; sie werden gegen die bekannte Scope-/Rollenliste
    validiert. Personen-/Open-Identitäten bleiben unverändert (Zugriff weiterhin
    rein rollenbasiert).
  - **Versionierter `/v1`-Router**: `POST /v1/schemas/{id}/instances`,
    `GET /v1/instances/{id}`, `GET /v1/instances/{id}/tasks`,
    `POST /v1/instances/{id}/nodes/{nodeId}/complete`,
    `POST /v1/instances/{id}/nodes/{nodeId}/decide`,
    `GET /v1/instances/{id}/data`, `PUT /v1/instances/{id}/data`. Die Endpunkte
    spiegeln die bestehende Laufzeitlogik (gleicher validate-before-commit-Pfad)
    und werden über Integrations-Scopes abgesichert; ein reines Service-Token
    wird auf seine Scopes eingeschränkt (Least Privilege), ohne Personen-Rollen
    einzuschränken.
  - **Idempotenz**: Mutierende `/v1`-Aufrufe akzeptieren einen
    `Idempotency-Key`-Header; eine Wiederholung mit gleichem Schlüssel liefert
    dieselbe erste Antwort zurück, ohne erneut auszuführen (kein Doppelstart,
    kein Doppelabschluss bei Netz-Retries). In-Memory-Variante; DB-Variante folgt.
  - **Datenschnittstelle**: `GET /v1/instances/{id}/data` liest alle
    Prozessvariablen; `PUT /v1/instances/{id}/data` setzt Werte mit
    Laufzeit-Typprüfung gegen die deklarierten Datenelement-Typen (D3 an der
    Grenze; unbekannte Elemente/Typfehler → 422).
  - Rein additiv, Boundary-only; der Kern bleibt unangetastet. Alle bestehenden
    Tests bleiben grün (382 Tests, +10 neue in `tests/test_integration_inbound.py`).
- **Integrationsschicht Phase P0 – Meta-Modell & Korrektheitsregeln (E11)**: Erste
  Bausteine der „maximal offenen“ externen Anbindung gemäß
  [docs/Integrations-Konzept-Externe-Anbindung.md](docs/Integrations-Konzept-Externe-Anbindung.md).
  - **Meta-Modell**: Neue Aufzählung `AutomationKind` (`MANUAL_NONE`,
    `EXTERNAL_TASK`, `HTTP_PUSH`) und additive Felder an `ServiceBinding`
    (`automation`, `topic`, `endpoint_ref`, `retry_max`, `retry_backoff_ms`,
    `request_timeout_ms`). Bestehende Schemata bleiben unverändert
    (`automation` ist standardmäßig `MANUAL_NONE`). Zusätzlich additive
    Laufzeit-Entitäten `ExternalTask`/`ExternalTaskState`, `Incident` und
    `WebhookSubscription` (vom Validator nie geprüft, für spätere Phasen).
  - **Operation** `set_automation(schema, node_id, automation, …)`: konfiguriert,
    wie ein automatischer Schritt von außen angesteuert wird; erzwingt eine
    bestehende Service-Bindung und `ACTIVITY` als Knotentyp (sonst `OP`).
  - **Korrektheitsregeln I1–I4** (Validator, „silent unless used“): I1 prüft die
    Wohlgeformtheit (`EXTERNAL_TASK` ⇒ Topic, `HTTP_PUSH` ⇒ Endpoint-Referenz),
    I2 die Konsistenz (automatisierte Bindung ist `automatic`, genau ein
    Ausführungsmuster), I3 die referenzielle Integrität der Parameterabbildung
    und I4 verhindert eingebettete Geheimnisse/URLs in Referenzfeldern.
  - Rein additiv: integrationsfreie Modelle erzeugen keinerlei I-Befund; alle
    bestehenden Tests bleiben grün (372 Tests, +14 neue in
    `tests/test_integration_rules.py`).

- **Ausgewählte Instanz im Monitoring hervorgehoben**: Beim Klick auf eine aktive
  Instanz in der Tabelle *Aktive Instanzen* (Monitoring) wird die zugehörige Zeile
  jetzt **farblich hervorgehoben**, solange ihr Detail unten geöffnet ist – so ist
  jederzeit ersichtlich, welche Instanz gerade betrachtet wird. Rein visuell im
  Web-Client, keine Modell-, Kern- oder API-Änderung.
- **Kontrollfluss-Canvas verschieb- und zoombar**: Die Kontrollflussansicht in
  **Modellieren** sowie die **Live-Prozesslandkarte** in **Ausführung** und
  **Monitoring** lassen sich jetzt frei bedienen:
  - **Verschieben (Pan)** per Ziehen mit der Maus in alle Richtungen (kein
    Festhängen mehr an den Scroll-Achsen).
  - **Zoomen** per Mausrad – stets **zur aktuellen Zeigerposition hin bzw. von
    ihr weg** (der Punkt unter dem Cursor bleibt fixiert), begrenzt auf 0,2×–4×.
  - Eine dezente Bedienhilfe („Mausrad: Zoom · Ziehen: Verschieben“) blendet sich
    in der Canvas-Ecke ein. Klicks auf Knoten und „+“-Operationen bleiben
    erhalten (ein abschließender Drag löst keine versehentliche Auswahl aus).
  - Rein visuell im Web-Client – keine Modell-, Kern- oder API-Änderung; der
    Pan/Zoom-Zustand setzt sich beim Neu-Rendern zurück.
- **Revision in der Schema-Benennung sichtbar**: Revisionen eines Modells (gleicher
  Name, eigene ID, hochgezählte Version) erschienen in der **Modellauswahl** bisher
  ununterscheidbar nebeneinander. Sie tragen jetzt überall die Revision in der
  Benennung (z. B. „Urlaubsantrag (v2)“):
  - in der **Modellauswahl** (Schema-Picker oben),
  - im **Monitoring** in der Spalte *Schema* der aktiven Instanzen,
  - in der **Aufgaben**-Sicht in der Spalte *Prozess*.
  - Die Aufgaben-Endpunkte (`GET /me/tasks`, `GET /agents/{id}/tasks`,
    `GET /instances/{id}/tasks`) liefern dafür additiv das neue Feld
    `schema_version` je Aufgabe; die Instanz führt ihre `schema_version` bereits.
    Rein additiv – kein bestehendes Verhalten geändert, kein Korrektheitskriterium
    berührt.
- **Rechtssicherer Haftungsausschluss zentral verankert**: Neue, zweisprachige
  [`DISCLAIMER.md`](DISCLAIMER.md) (deutsch maßgeblich, englische Zusammenfassung)
  schließt – soweit gesetzlich zulässig – jede Haftung sowohl für die
  **Inbetriebnahme/den Betrieb** (Schäden an Servern, Betriebssystem, paralleler
  oder anderer Software, Netzwerken, Infrastruktur) als auch für die **Nutzung**
  (Datenverlust/-beschädigung, fehlerhafte Prozesse, Betriebsunterbrechung) aus;
  mit salvatorischer Klausel für gesetzlich zwingende Haftung (u. a. Leben/Körper/
  Gesundheit, Vorsatz/grobe Fahrlässigkeit, ProdHaftG). Verankert in
  `README.md`, `SECURITY.md`, `core/README.md`, der Landingpage (`site/`), dem
  Web-Client (Login-Overlay und Fußzeile) sowie den Anleitungen
  `docs/Windows-Server-Setup.md` und `docs/Mitarbeiter-Anleitung.md`.
- **Live-Aktualisierung der Laufzeit-Sichten**: Wird der Fortschritt einer
  Aktivität/Instanz aktualisiert (z. B. eine Aufgabe von einem anderen Nutzer
  abgeschlossen), aktualisieren sich die **Aufgabenlisten**, die **Ausführen**-
  Sicht und das **Monitoring** im Web-Client automatisch – ohne manuelles
  Neuladen.
  - Neuer schlanker Endpunkt `GET /monitoring/revision` (Leserechte) liefert
    einen monoton steigenden Revisionszähler aus dem Audit-Log
    (`AuditLog.revision()` für In-Memory- und SQLAlchemy-Backend).
  - Der Web-Client pollt diesen Zähler im Hintergrund (alle 4 s) und rendert die
    aktuelle Laufzeit-Sicht nur bei tatsächlicher Änderung neu. Modellier-Sichten
    sowie offene Dialoge/Formulareingaben bleiben unangetastet.
- **Sicht bleibt beim Neuladen erhalten**: Die aktive Sicht (z. B. Monitoring)
  wird in `localStorage` gemerkt; ein Seiten-Reload stellt sie wieder her,
  statt immer auf „Modellieren“ zurückzufallen.
### Geändert
- **Beispieldaten zeigen wandernde Datenobjekte**: Die Demo-Prozesse
  demonstrieren jetzt Datenobjekte, die zwischen Aufgaben befüllt und
  weitergegeben werden. Im `urlaubsantrag` wandert zusätzlich zur `tage`-Variable
  ein angereichertes Objekt `entscheidung` durch den Fluss (von beiden
  XOR-Zweigen geschrieben, von der Benachrichtigung gelesen). Im `beschaffung`
  werden `betrag` und `budget_ok` auf parallelen Zweigen befüllt und am AND-Join
  zusammengeführt (zuvor war `betrag` deklariert, aber nicht verdrahtet). Die
  abgeschlossene Demo-Instanz trägt die real weitergereichten Werte.


### Hinzugefügt
- **Beispieldaten & administrativer Reset**: Ein eingebauter Demo-Datensatz
  (`procworks/demo.py`) macht alle Funktionen sofort greifbar – die geteilte
  Organisation `org-acme`, der **freigegebene** Prozess „Urlaubsantrag“, der
  **Entwurf** „Beschaffung“ und **drei Instanzen** an unterschiedlichen Punkten
  (frisch gestartet, in Genehmigung wartend, abgeschlossen) inklusive
  Audit-Verlauf und KPIs.
  - Neuer **administrator-exklusiver** Endpunkt `POST /admin/reset`
    (`require_role("admin")`, sonst HTTP 403): setzt das System **auf Null**
    (Schemata, Instanzen, Organisationsmodelle, Audit-Log) und lädt die
    Beispieldaten optional wieder (`{"load_demo": true}`). Im Passwort-Login
    werden zusätzlich alle Nutzerkonten entfernt – **außer** dem Bootstrap-`admin`
    und der handelnden Administrator-Identität (kein Aussperren). Die Antwort
    liefert die neuen Bestände (`schemas`, `instances`, `org_models`, `users`).
  - Alle Stores erhielten dafür ein additives `clear()`
    (`SchemaStore`/`InstanceStore`/`OrgStore`/`AuditLog`, jeweils in-memory und
    SQLAlchemy).
  - Der Web-Client zeigt das als Bereich **„Wartung (Administrator)“** in der
    Monitoring-Sicht (zwei Aktionen mit Bestätigungsdialog), nur für die Rolle
    `admin` sichtbar.
  - **Test-Logins** für die Beispieldaten (Passwort `demo-procworks`):
    `mara.modell` (Modellierer), `erika.sander` (Bearbeiter), `tom.berger`
    (Bearbeiter/Leitung), `vera.viewer` (Leser). Sie entstehen beim Laden der
    Beispieldaten im Passwort-Login und sind im README-Schnellstart sowie der
    Windows-Server-Anleitung dokumentiert.
  - Der README bekam einen **Schnellstart „In 15 Minuten einsatzbereit“**
    (Windows Server als Standard, dazu macOS/Linux) für mittelständische
    Unternehmen ohne eigene IT-Abteilung.
- **RBAC-Verfeinerung & Test-Instanzen für Entwürfe**: Der `Modellierer`
  (`modeler`) ist jetzt zugleich betroffener Mitarbeiter – er darf Aufgaben über
  „Meine Aufgaben“ bearbeiten, Instanzen ausführen und **eigene Entwürfe als
  Test-Instanz starten** (Sicht „Ausführung“ + „Meine Aufgaben“ sind für ihn
  sichtbar). `operator` behält Ausführung/Aufgaben/Monitoring (lesend),
  `viewer` bleibt rein lesend (nur Monitoring, kein Instanzstart).
  - Nicht freigegebene (Entwurf-)Schemata können von `modeler`/`admin` als
    `is_test`-markierte Wegwerf-Instanz gestartet werden. Test-Instanzen
    schreiben **keine** Audit-Events und sind damit aus den Monitoring-KPIs,
    der Process-Map und der Timeline ausgeschlossen. Der Engine-Aufruf
    `instantiate(..., allow_unreleased=…, is_test=…)` und das Feld
    `ProcessInstance.is_test` sind additiv.
  - Produktionsbetrieb läuft standardmäßig im **Passwort-Login**
    (`PROCWORKS_AUTH=password` in `deploy/docker-compose.full.yml` und im
    Helm-Chart `api.authMode`); der offene Modus bleibt nur für Dev/Test. Beim
    ersten Start eines leeren Credential-Stores wird automatisch ein
    `admin`-Konto mit zufälligem Einmal-Passwort angelegt und ins Server-Log
    geschrieben (erzwungener Passwortwechsel bei der ersten Anmeldung).

- Konzeptgetriebene, **additive** Tool-Erweiterungen aus der Roadmap §13.1
  umgesetzt – ohne ein bestehendes Korrektheitskriterium zu lockern und mit
  eigenen Tests (Kern weiterhin vollständig grün, 338 Tests):
  - **E7 – Modellmetriken & 7PMG-Hinweise** (`procworks/metrics.py`): rein
    lesende Kennzahlen (Knotenzahl, Verschachtelungstiefe, Gateway-Heterogenität,
    Konnektorgrad) und nicht-blockierende Hinweise (G1/G2/G6/G7). Endpunkt
    `GET /schemas/{id}/metrics`. Beeinflusst Stufe A/B nicht.
  - **E3 – Wertschöpfungs-Klassifikation** (`ValueClass`, optionales
    `Node.value_class`): Operation `set_value_class`, Aggregation
    `value_class_breakdown`, Endpunkt `POST /schemas/{id}/value-class`.
  - **E8 – Arbeitslisten-Priorität** (`WorkItemPriority`, `ImpactUrgency`,
    `PriorityLevel`): abgeleitete Priorität = Auswirkung + Dringlichkeit,
    Sortierung der offenen Aufgaben (`OpenTask.priority`), Operation
    `set_node_priority`, Endpunkt `POST /schemas/{id}/priority`.
  - **E5 (statisch) – Zeitliche Perspektive T1/T2** (`TimeConstraint`,
    `ProcessSchema.deadline_seconds`): additive Validierungsgruppe, die nur bei
    vorhandenen Zeitangaben greift – T1 (Wohlgeformtheit) und T2 (kritischer
    Pfad ≤ Frist). Operationen `set_time_constraint`/`set_deadline`, Endpunkte
    `POST /schemas/{id}/time-constraint` und `POST /schemas/{id}/deadline`.
  - **E4 (teilweise) – Leistungs-KPIs**: `KpiReport` um die Flexibilitäts-
    Dimension (`adhoc_instances`, `flexibility_adhoc_ratio`) erweitert; Zeit
    bleibt über die Zykluszeit abgedeckt. **Kosten/Qualität bewusst offen**
    (keine Daten erfasst – ehrliche Lücke, vgl. §8.4.1/§13.1).
  Die laufzeit-invasiven Roadmap-Punkte (E1/E2/E6/E9 sowie der Timer-Teil von
  E5 und Kosten/Qualität in E4) bleiben **bewusst offen** und sind in §13.1
  ehrlich als solche ausgewiesen.
- Konzept (`docs/Architektur-Konzept-Prozessmodellierung.md`, v0.9) um Konzepte
  aus ergänzenden Fachquellen erweitert (in eigener Formulierung, mit sauberen
  Quellenangaben): Experten-Priorisierung der 7PMG und Einordnung in den
  SEQUAL-Qualitätsrahmen samt präziser GoM-Zitierung (§2.4.1), Eskalations- und
  Prioritätsmodell aus dem IT-Service-Management – funktionale/hierarchische
  Eskalation und Priorität = Auswirkung + Dringlichkeit mit SLA-gebundenen
  Fristen (§3.8, §6.2.1), sowie Einordnung der drei Flexibilitätsdimensionen
  (Entwurfszeit/Ausführungszeit/Schemaevolution) in die ProcWorks-Mechanismen
  (neuer §6.5). Roadmap um additive Toolanpassungen E8 (Arbeitslisten-Priorität)
  und E9 (mehrstufige Eskalation) ergänzt (§13.1); erweiterte Quellenliste
  (§15.1: [KSJ06], [BRU00], [WRR08], [DRR10], [Olb12]). Es werden ausschließlich
  öffentlich zugängliche, rechtlich zulässige Quellen verwendet.
- Konzept (`docs/Architektur-Konzept-Prozessmodellierung.md`, v0.8) fachlich
  vertieft und mit Originalquellen belegt: Modellqualitäts-Dimensionen
  syntaktisch/semantisch/pragmatisch samt ehrlicher Einordnung der
  Correctness-by-Construction-Reichweite (§3.7), Bezug der Modellierungsregeln zu
  7PMG und GoM (§2.4.1), Einordnung als PAIS mit sechs Prozessperspektiven (§5.5),
  Lebenszyklus eines Arbeitslisten-Eintrags aus Bearbeitersicht (§6.2.1),
  zeitliche Perspektive T1–T3 als Roadmap-Kriterien (§3.8), Leistungssicht mit
  vier Dimensionen (Zeit/Kosten/Qualität/Flexibilität) und
  Wertschöpfungs-Klassifikation für das Monitoring (§8.4.1). Neue Roadmap-Tabelle
  mit vorbereiteten, additiven Toolanpassungen (§13.1) und erweiterte
  Quellenliste mit Zitierschlüsseln (§15.1: [LSS94], [Ros96], [MRA10], [MNV07],
  [Dum+13], [HC94], [RW12], [LRW16]).
- `delete_node` entfernt jetzt beim Löschen des letzten Knotens eines
  Verzweigungszweigs den Zweig selbst (statt eine leere Split-→-Join-Kante zu
  hinterlassen). Bleibt danach nur **ein** Zweig einer XOR- oder UND-Verzweigung
  übrig, wird die gesamte Verzweigung (Split und passender Join) aufgelöst und
  der verbliebene Zweig inline zwischen Vorgänger und Nachfolger behalten.
- Modellbearbeitung im Web-Editor: ausgewählte Knoten lassen sich jetzt direkt
  umbenennen und entfernen. Zwei neue korrektheitserhaltende Kern-Operationen
  `rename_node(schema, node_id, label)` (nur Aktivität/Teilprozess, Schema muss
  editierbar sein) und `delete_node(schema, node_id)` über `validate-before-commit`.
  `delete_node` entfernt eine Aktivität/einen Teilprozess nur auf serieller
  Strecke und schließt die Lücke; bei einem Split wird der gesamte von Split und
  passendem Join eingeschlossene SESE-Block samt Zweigknoten und davon
  abhängiger Staff-/Service-/Daten-Bindungen entfernt. Start/Ende und Join-Knoten
  sind geschützt. Neue API-Endpunkte `PATCH /schemas/{id}/nodes/{nodeId}` und
  `DELETE /schemas/{id}/nodes/{nodeId}`. Web-Client: neues „Knoten"-Panel in der
  Modellierungssicht mit Umbenennen-Feld und Entfernen-Aktion (Verzweigung
  entfernt den ganzen Block).
- Beim Auswählen eines Knotens wird das Modell so verschoben, dass das selektierte
  Element in der Mitte der Kontrollfluss-Ansicht liegt (kein Zurückspringen mehr
  an den Anfang).
- Passwort-Login für eigenständige Deployments ohne externen Identity-Provider
  (Auth-Konzept Abschnitt 11): drittes `AuthBackend` `PasswordAuthBackend`
  (`PROCWORKS_AUTH=password`). Login-Name wird aus dem Agentennamen vorgeschlagen
  (`vorname.nachname`, Umlaut-Transliteration, Kollisions-Suffix) und in einem
  separaten `CredentialStore` (`InMemoryCredentialStore`/`SqlAlchemyCredential‐
  Store`) gehalten – getrennt vom Agenten-/Org-Modell. Passwörter werden mit
  `hashlib.scrypt` (Standardbibliothek, kein neues Paket) gesalzen gehasht;
  Sessions sind opake Bearer-Token (nur als SHA-256-Digest im Speicher).
  Initialpasswort mit erzwungener Änderung beim ersten Login; danach direkter
  Login. Neue Endpunkte `GET /auth/config`, `POST /auth/login`,
  `POST /auth/change-password`, `POST /auth/logout` sowie Admin-Verwaltung
  `GET/POST /users`, `POST /users/{login}/reset-password`,
  `DELETE /users/{login}`. Initial-Admin-Bootstrap über `PROCWORKS_ADMIN_LOGIN`
  /`PROCWORKS_ADMIN_PASSWORD`, Session-Dauer über
  `PROCWORKS_SESSION_TTL_MINUTES`. Migration `0005_user_credential`. Web-Client:
  Vollbild-Login auf der Index-Seite, erzwungene Passwortvergabe, „Passwort
  ändern" und „Abmelden" in der Seitenleiste sowie in der Ressourcensicht je
  Agentenzeile ein Button „Login" (nur Admin/Passwort-Modus), der den Login aus
  dem Agentennamen vorschlägt und das Initialpasswort einmalig anzeigt.
- Authentifizierung & rollenbasierte Zugriffskontrolle (Auth-Konzept Variante C):
  austauschbarer `AuthBackend` (analog `SchemaStore`) mit Standard-Modus „offen"
  (`OpenAuthBackend`, Entwicklung) und Token-Backend (`TokenAuthBackend`, gegen
  eine Token-Datei). Neue Module `auth.py` + `auth_token.py`, `Principal` mit
  gebundener Bearbeiter-Identität (`agent_id`). Grobe Rollen `admin`, `modeler`,
  `operator`, `viewer` schützen jeden API-Endpunkt; die feingranulare
  BZR-Eignungsprüfung im Kern bleibt unverändert. Neuer Endpunkt `GET /auth/me`
  sowie `GET /me/tasks` (eigene Arbeitsliste der angemeldeten Person). Die
  Impersonation-Lücke ist geschlossen: `complete`/`decide` nehmen die handelnde
  Identität aus dem `Principal`, nicht mehr aus dem Request-Body; das Audit-Log
  führt die echte Identität. CORS über `PROCWORKS_CORS_ORIGINS` konfigurierbar.
  Konfiguration via `PROCWORKS_AUTH` (`open`/`token`) und `PROCWORKS_TOKENS`.
  Web-Client: Login per Bearer-Token, Rollen-Pill, rollenabhängige Navigation
  und „Meine Aufgaben" für die angemeldete Person.
- Geteilte, modellübergreifende Organisationsmodelle: Eine Organisation kann
  einmal modelliert und in mehreren Prozessmodellen verwendet werden. Schemata
  verweisen per `org_model_id` live auf eine zentral gepflegte Organisation
  (Stammdaten-Registry); Änderungen wirken sofort in allen verknüpften Modellen
  und laufenden Instanzen. Neues Modul `org.py`, `OrgStore`/`SqlAlchemyOrgStore`,
  Migration `0004_org_model`, REST-Endpunkte unter `/org-models` sowie
  Verknüpfen/Lösen über `/schemas/{id}/org-model`. Org-Änderungen werden gegen
  alle referenzierenden Schemata revalidiert (Correctness by Construction über
  die Modellgrenze). Web-Client: geteilte Organisation anlegen, auswählen,
  verknüpfen und zentral pflegen.
- CI-/Release-Gerüst unter `.github/` (GitHub Actions, Trivy-Scan, Dependabot).
- Community-Dateien: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- Issue-/Pull-Request-Templates und `CODEOWNERS`.

[Unveröffentlicht]: https://github.com/tobiasHaecker/procworks/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/tobiasHaecker/procworks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tobiasHaecker/procworks/releases/tag/v0.1.0
