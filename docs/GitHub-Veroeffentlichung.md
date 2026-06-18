# Veröffentlichung auf GitHub – Schritt für Schritt

Diese Anleitung führt das Projekt von einem lokalen Ordner zu einem öffentlichen
GitHub-Repository unter der Business Source License 1.1 (BUSL-1.1). Befehle sind
für **Windows PowerShell** formuliert und werden im Projektordner ausgeführt.

> Voraussetzung: Ein kostenloses GitHub-Konto. Optional die GitHub-CLI (`gh`)
> für einen schnelleren Weg (siehe Variante B in Schritt 5).

---

## Schritt 0 – Git installieren und einmalig einrichten

1. Git installieren: <https://git-scm.com/download/win> (oder `winget install Git.Git`).
2. PowerShell neu öffnen und prüfen:

   ```powershell
   git --version
   ```

3. Namen und E-Mail für Commits einmalig setzen (erscheinen in der Commit-Historie):

   ```powershell
   git config --global user.name "Tobias Häcker"
   git config --global user.email "DEINE-EMAIL@example.com"
   ```

   > Tipp: GitHub bietet eine anonyme No-Reply-Adresse
   > (`Settings ? Emails ? Keep my email addresses private`), falls die echte
   > E-Mail nicht öffentlich werden soll.

---

## Schritt 1 – In den Projektordner wechseln

```powershell
Set-Location "C:\Pfad\zu\ProcWorks"
```

---

## Schritt 2 – Sicherstellen, dass nichts Unerwünschtes eingecheckt wird

Die Datei `.gitignore` ist bereits vorhanden und schließt u. a. `.venv/`
(inkl. der lokal installierten Node-Umgebung), `node_modules/` und `docs/*.pdf`
aus. Kurz kontrollieren:

```powershell
Get-Content .gitignore
```

> Wichtig: Der Ordner `.venv` darf **nicht** ins Repository – er ist groß und
> rechnerspezifisch. Die CI installiert ihre Werkzeuge selbst.

---

## Schritt 3 – Repository lokal anlegen und ersten Commit erstellen

```powershell
git init -b main
git add .
git status        # Kontrolle: .venv/ darf NICHT auftauchen
git commit -m "Initiale Veröffentlichung: Konzept, Prototyp, CI"
```

Falls in `git status` doch `.venv/` erscheint, war die `.gitignore` noch nicht
aktiv – dann vor dem Commit Folgendes ausführen:

```powershell
git rm -r --cached .venv 2>$null
git add .gitignore
```

---

## Schritt 4 – Leeres Repository auf GitHub erzeugen

Variante A (Weboberfläche):

1. <https://github.com/new> öffnen.
2. **Repository name** z. B. `procworks` eintragen.
3. **Description** (optional): „Stabile Prozessmodellierung mit Correctness by Construction".
4. Sichtbarkeit **Public** wählen.
5. **Keine** Initialisierung anhaken (kein README, keine .gitignore, keine Lizenz –
   diese Dateien sind bereits lokal vorhanden).
6. **Create repository** klicken. GitHub zeigt anschließend die Repo-URL an.

---

## Schritt 5 – Lokales Repo mit GitHub verbinden und hochladen

Variante A – mit der von GitHub angezeigten URL (HTTPS):

```powershell
git remote add origin https://github.com/DEIN-BENUTZERNAME/procworks.git
git push -u origin main
```

Beim ersten Push öffnet sich ein Anmeldefenster (Browser-Login oder Personal
Access Token). Danach ist der Code online.

Variante B – komplett über die GitHub-CLI (ersetzt Schritt 4 und 5):

```powershell
winget install GitHub.cli      # falls noch nicht vorhanden
gh auth login                  # einmalige Anmeldung
gh repo create procworks --public --source=. --remote=origin --push
```

---

## Schritt 6 – Repository-Profil schärfen

1. Auf der Repo-Seite rechts bei **About** ein Zahnrad anklicken:
   - **Description** und ggf. **Website** setzen.
   - **Topics** vergeben, z. B. `bpmn`, `workflow`, `process-management`,
     `correctness-by-construction`, `open-source`.
2. GitHub erkennt die Datei `LICENSE` automatisch. Da die Business Source License
   keine von GitHub auto-erkannte SPDX-Standardlizenz ist, kann rechts „Other" oder
   „BUSL-1.1" erscheinen – das ist korrekt; der vollständige Lizenztext steht in
   `LICENSE`.
3. Das `README.md` wird automatisch auf der Startseite gerendert.

---

## Schritt 7 – Continuous Integration (Actions) prüfen

Die Datei `.github/workflows/ci.yml` startet **automatisch** beim ersten Push.

1. Reiter **Actions** öffnen – der CI-Lauf „CI" sollte erscheinen.
2. Jobs:
   - **docs-lint** – Markdown-Lint + Link-Check.
   - **prototype-check** – HTML-Validierung des Prototyps.
3. Bei Grün erscheint ein Häkchen am Commit. Das Badge im README verlinkt darauf.

> Lokal lassen sich dieselben Prüfungen jederzeit ausführen (siehe Anhang).

---

## Schritt 8 – Branch-Schutz für `main` (empfohlen)

1. **Settings ? Branches ? Add branch ruleset** (oder „Add rule").
2. Branch-Name-Muster: `main`.
3. Aktivieren:
   - **Require a pull request before merging**.
   - **Require status checks to pass** ? die CI-Checks auswählen.
4. Speichern. Dadurch landet nichts Ungeprüftes mehr direkt auf `main`.

---

## Schritt 9 – Den Prototyp als Web-Demo veröffentlichen (optional, GitHub Pages)

Da der Prototyp eine statische HTML-Datei ist, lässt er sich kostenlos hosten:

1. **Settings ? Pages**.
2. **Source**: `Deploy from a branch`, Branch `main`, Ordner `/ (root)`.
3. Speichern. Nach kurzer Zeit ist die Demo erreichbar unter:
   `https://DEIN-BENUTZERNAME.github.io/procworks/prototype/`

> Alternativ kann der Ordner `prototype/` als eigene Pages-Quelle dienen, wenn
> später eine Landing-Page im Wurzelverzeichnis liegt.

---

## Schritt 10 – Eine erste Version markieren (Release)

```powershell
git tag -a v0.1.0 -m "Konzept + klickbarer Prototyp"
git push origin v0.1.0
```

Anschließend auf GitHub unter **Releases ? Draft a new release** den Tag `v0.1.0`
wählen, Titel und Notizen ergänzen, **Publish release**.

---

## Schritt 11 – Laufende Pflege

- **Dependabot** (Datei `.github/dependabot.yml`) schlägt wöchentlich Updates der
  GitHub-Actions als Pull Request vor – einfach prüfen und mergen.
- Neue Änderungen immer über einen Branch + Pull Request einbringen, damit die
  CI prüft und der `main`-Branch stabil bleibt:

  ```powershell
  git switch -c feature/meine-aenderung
  # ... bearbeiten ...
  git add .
  git commit -m "Beschreibung der Änderung"
  git push -u origin feature/meine-aenderung
  ```

  Danach auf GitHub den **Pull Request** öffnen.

---

## Anhang – Prüfungen lokal ausführen

Node ist in der Python-`.venv` mitinstalliert. Damit lassen sich die CI-Prüfungen
vorab lokal ausführen:

```powershell
# HTML-Prototyp validieren
& ".venv\Scripts\npm.cmd" exec --yes -- html-validate "prototype/**/*.html"

# Markdown prüfen
& ".venv\Scripts\npm.cmd" exec --yes -- markdownlint-cli2 "**/*.md" "#node_modules" "#.venv"
```

Beide Befehle sollten ohne Fehler (Exit-Code 0) durchlaufen.
