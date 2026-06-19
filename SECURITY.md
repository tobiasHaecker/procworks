# Richtlinie zur Meldung von Sicherheitslücken

Die Sicherheit von ProcWorks ist uns wichtig. Danke, dass du Schwachstellen
verantwortungsvoll offenlegst.

## Unterstützte Versionen

Das Projekt befindet sich in aktiver Entwicklung. Sicherheitsfixes werden gegen
den `main`-Branch bereitgestellt.

| Version | Unterstützt |
| ------- | ----------- |
| `main`  | ✅          |
| ältere Tags | ❌      |

## Eine Schwachstelle melden

**Bitte melde Sicherheitslücken nicht über öffentliche GitHub-Issues.**

Nutze stattdessen einen der folgenden vertraulichen Kanäle:

- Bevorzugt: **GitHub Security Advisories** über den Reiter *Security* →
  *Report a vulnerability* dieses Repositorys.
- Alternativ: per E-Mail an `kontakt@procworks.de`.

Bitte gib so viele Details wie möglich an:

- betroffene Komponente/Datei und Version bzw. Commit,
- eine Beschreibung der Schwachstelle und ihrer Auswirkung,
- eine Schritt-für-Schritt-Anleitung zur Reproduktion (Proof of Concept),
- mögliche Gegenmaßnahmen, falls bekannt.

## Ablauf

1. **Eingangsbestätigung** innerhalb von 72 Stunden.
2. **Bewertung & Triage**: Wir prüfen den Bericht und melden uns mit einer
   ersten Einschätzung zurück.
3. **Behebung**: Wir entwickeln einen Fix und koordinieren mit dir einen
   Zeitpunkt für die Offenlegung.
4. **Veröffentlichung**: Nach dem Fix wird die Schwachstelle in den
   Release-Notes dokumentiert; auf Wunsch nennen wir dich als Finder.

Wir bitten um **Coordinated Disclosure**: Bitte veröffentliche Details erst,
nachdem ein Fix verfügbar ist.

## Authentifizierung & Betrieb

Die API trägt eine austauschbare Auth-Schicht am Boundary (`auth.py`,
Auth-Konzept Variante C). Hinweise für den produktiven Betrieb:

- **Standardmodus ist „offen"** (`PROCWORKS_AUTH=open`): keine Identitätsprüfung,
  alle Rollen freigegeben. Dieser Modus ist ausschließlich für die lokale
  Entwicklung gedacht und darf **nicht** öffentlich exponiert werden.
- **Produktiv** `PROCWORKS_AUTH=token` setzen und Tokens über `PROCWORKS_TOKENS`
  (JSON-Datei) bereitstellen. Tokens werden nur als SHA-256-Digest gehalten.
  Die Token-Datei gehört nicht ins Repository und sollte restriktive
  Dateirechte erhalten.
- **Passwort-Login** (`PROCWORKS_AUTH=password`) für Deployments ohne externen
  IdP: Zugangsdaten liegen in einem separaten `CredentialStore` (nicht im
  Modell). Passwörter werden mit `hashlib.scrypt` pro Nutzer gesalzen gehasht
  und konstant-zeitlich verglichen; Klartext wird nie gespeichert. Login-
  Sessions sind opake Bearer-Token, nur als SHA-256-Digest im Speicher
  gehalten (Neustart erzwingt erneutes Login). Neue Nutzer erhalten ein
  zufälliges Initialpasswort mit erzwungener Änderung beim ersten Login
  (min. 8 Zeichen, ungleich dem alten). Der Initial-Admin wird über
  `PROCWORKS_ADMIN_LOGIN`/`PROCWORKS_ADMIN_PASSWORD` provisioniert – diese
  Variablen als Secrets behandeln und nach dem ersten Login-/Passwortwechsel
  nicht dauerhaft im Klartext halten. Session-Dauer über
  `PROCWORKS_SESSION_TTL_MINUTES`.
- **CORS** über `PROCWORKS_CORS_ORIGINS` (kommagetrennt) auf die tatsächlich
  erlaubten Ursprünge einschränken; der Default `*` ist nur für die Entwicklung.
- Die handelnde Bearbeiter-Identität wird bei `complete`/`decide` aus dem
  verifizierten `Principal` abgeleitet, niemals aus dem Request-Body
  (Impersonation-Schutz). Die feingranulare BZR-Eignungsprüfung im Kern bleibt
  als zusätzliche Schutzschicht aktiv.
