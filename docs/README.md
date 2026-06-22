<!-- SPDX-License-Identifier: BUSL-1.1 -->
# ProcWorks – Dokumentationsübersicht

Diese Seite ist der **Einstieg in die gesamte Dokumentation**. Sie führt nach
**Rolle** zur jeweils passenden Anleitung und listet darunter alle weiteren
Dokumente.

> Neu hier? Im Web-Client gibt es zusätzlich die Sicht **„Hilfe"** mit einer
> Kurzübersicht aller Sichten und einem Glossar der Regel-Codes.

---

## Nach Rolle

### 🧩 Modellierer (Prozesse erstellen)
Prozesse von Grund auf modellieren, mit Daten und Bearbeitern verdrahten, testen
und freigeben.
→ **[Modellierer-Anleitung.md](Modellierer-Anleitung.md)**

### 🧑‍💼 Sachbearbeiter (Aufgaben bearbeiten)
Anmelden, persönliche Arbeitsliste sehen, Aufgaben erledigen. Enthält auch den
Teil, den der Administrator einmalig vorbereitet.
→ **[Mitarbeiter-Anleitung.md](Mitarbeiter-Anleitung.md)**

### 🛠️ Administrator (Installation & Betrieb)
Erstinstallation auf Windows Server (WSL2 → Docker → Start → Logins → Update/Backup),
Beispieldaten und Reset.
→ **[Windows-Server-Setup.md](Windows-Server-Setup.md)**
Schneller Einstieg auch im Repo-[README](../README.md#schnellstart-in-15-minuten-einsatzbereit).

### 🔌 Integrator (Fremdsysteme anbinden)
Die offene `/v1`-Schnittstelle: Instanzen starten, Aufgaben schließen,
External-Tasks, Daten-Connectoren, Webhooks/HTTP-Push.
→ **[Integrations-Leitfaden.md](Integrations-Leitfaden.md)**
Hintergrund/Design: [Integrations-Konzept-Externe-Anbindung.md](Integrations-Konzept-Externe-Anbindung.md)

---

## Konzept & Architektur

| Dokument | Inhalt |
|----------|--------|
| [Architektur-Konzept-Prozessmodellierung.md](Architektur-Konzept-Prozessmodellierung.md) | Hauptquelle: Correctness by Construction, Korrektheitskriterien (K/D/C/Z/A/H/F/T/I/B/M/R), Meta-Modell, Architektur, Roadmap |
| [Auth-Konzept.md](Auth-Konzept.md) | Pluggable Authentifizierung (offen/Token/Passwort), Rollen & RBAC |
| [Integrations-Konzept-Externe-Anbindung.md](Integrations-Konzept-Externe-Anbindung.md) | Konzept der offenen API-Anbindung (Inbound/Outbound/Daten/Webhooks) |

## Betrieb & Anbindung

| Dokument | Inhalt |
|----------|--------|
| [Windows-Server-Setup.md](Windows-Server-Setup.md) | Schritt-für-Schritt-Erstinstallation und Betrieb |
| [Integrations-Leitfaden.md](Integrations-Leitfaden.md) | Praktischer `/v1`-Leitfaden für Integratoren |
| [Mitarbeiter-Anleitung.md](Mitarbeiter-Anleitung.md) | Anleitung für Sachbearbeiter (zum Weitergeben) |
| [Modellierer-Anleitung.md](Modellierer-Anleitung.md) | Anleitung für Modellierer |

## Projekt & Veröffentlichung

| Dokument | Inhalt |
|----------|--------|
| [Marketing-Konzept.md](Marketing-Konzept.md) | Vermarktung, SEO, Domain procworks.de |
| [GitHub-Veroeffentlichung.md](GitHub-Veroeffentlichung.md) | Anleitung zur Veröffentlichung auf GitHub |

## Im Repository-Stamm

- [README.md](../README.md) – Projektüberblick und Schnellstart
- [core/README.md](../core/README.md) – Backend-Kern, API-Endpunkte, Entwicklung
- [CHANGELOG.md](../CHANGELOG.md) · [CONTRIBUTING.md](../CONTRIBUTING.md) ·
  [SECURITY.md](../SECURITY.md) · [DISCLAIMER.md](../DISCLAIMER.md) ·
  [GOVERNANCE.md](../GOVERNANCE.md)

---

> ⚠️ Nutzung auf eigenes Risiko, ohne Gewähr und ohne Haftung. Details:
> [DISCLAIMER.md](../DISCLAIMER.md).
