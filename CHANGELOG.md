# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei
dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

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

[Unveröffentlicht]: https://github.com/tobiasHaecker/procworks/commits/main
