# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei
dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt
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
