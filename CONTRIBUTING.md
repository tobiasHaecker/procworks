# Beitragen zu ProcWorks

Danke, dass du zu ProcWorks beitragen möchtest! Dieses Dokument fasst die
wichtigsten Konventionen für Code, Commits und Pull Requests zusammen.

ProcWorks folgt dem Leitprinzip **Correctness by Construction**: Der Kern lässt
keine inkorrekten Prozessmodelle zu (Validate-before-Commit). Beiträge müssen
dieses Prinzip respektieren — Korrektheitslogik gehört in den Kern, nicht in die
GUI.

## Verhaltenskodex

Mit deiner Teilnahme akzeptierst du den [Verhaltenskodex](CODE_OF_CONDUCT.md).

## Entwicklungsumgebung

Der API-Kernel liegt unter [`core/`](core/) (Python 3.12+).

```bash
cd core
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Qualitäts-Gates (vor jedem Commit)

Dieselben Prüfungen laufen in der CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
und müssen lokal grün sein:

```bash
cd core
ruff check .        # Linting / Imports
mypy src            # Typprüfung (--strict ist in pyproject.toml aktiv)
pytest -q           # Testsuite
```

Richtlinien:

- **Tests sind Pflicht.** Jede Verhaltensänderung braucht einen Test; neue
  Korrektheitsregeln gehören mit positiven *und* negativen Fällen abgedeckt.
- **Typen vollständig.** `mypy --strict` muss ohne Fehler durchlaufen.
- **Keine Umgehung des Validators.** Mutationen laufen über den
  Validate-before-Commit-Pfad — keine Direktmanipulation am Modell.

## Commits & Branches

- **[Conventional Commits](https://www.conventionalcommits.org/)**, z. B.
  `feat: parallelInsert für verschachtelte Blöcke`, `fix: …`, `docs: …`,
  `test: …`, `refactor: …`, `chore: …`.
- **[Semantic Versioning](https://semver.org/)** für Releases (siehe
  [Releases & Versionierung](#releases--versionierung)).
- Arbeite auf einem Feature-Branch und stelle einen Pull Request gegen `main`.

## Pull Requests

1. Halte den PR fokussiert (eine logische Änderung).
2. Beschreibe **Was** und **Warum**; verlinke zugehörige Issues.
3. Stelle sicher, dass CI grün ist (Lint, Typen, Tests).
4. Aktualisiere Doku/`CHANGELOG`, wenn sich Verhalten oder API ändern.

## Releases & Versionierung

`main` ist immer integrierbar: Jeder Push/PR durchläuft die CI (Lint, Typen,
Tests, Lizenz-Scan). Das ist **Continuous Integration** — noch **kein** Release.

Ein **Release** ist ein annotierter Tag `vX.Y.Z` auf `main`. Sein Push startet
den Workflow [`release.yml`](.github/workflows/release.yml), der die **API-** und
**Web-Container-Images** baut, mit **Trivy** (CRITICAL/HIGH) scannt und nach
**ghcr.io** veröffentlicht (Image-Tags `X.Y.Z`, `X.Y`, `sha`). Ein Release ist
damit ein fixierter, gescannter, reproduzierbar auslieferbarer Stand.

### Wann taggen?

Getaggt wird ein **kohärenter, dokumentierter, grüner** Stand, der ausgeliefert
werden soll (ein abgeschlossenes Feature-/Fix-Bündel mit aktuellem `CHANGELOG`) —
nicht jeder einzelne Commit.

Versionssprung nach [SemVer](https://semver.org/lang/de/) (Vorabphase `0.y.z`):

| Erhöhung | Wofür |
| --- | --- |
| **PATCH** (`0.y.Z`) | nur Bugfixes, Sicherheits-Patches, Doku — keine neuen Endpunkte/Felder. |
| **MINOR** (`0.Y.0`) | neue Funktionen/Endpunkte, additive Modelländerungen. Brechende Änderungen sind vor `1.0.0` erlaubt, müssen aber im `CHANGELOG` als **BREAKING** ausgewiesen werden. |
| **MAJOR** (`X.0.0`) | ab `1.0.0` für jede brechende Änderung. |

### Release-Checkliste

1. `CHANGELOG.md`: Abschnitt `[Unveröffentlicht]` zu `[X.Y.Z] - YYYY-MM-DD`
   schließen, neuen leeren `[Unveröffentlicht]`-Block anlegen, Vergleichslinks
   unten pflegen.
2. Version anheben (muss dem Tag ohne `v` entsprechen): `core/pyproject.toml`
   sowie `deploy/helm/Chart.yaml` (`version` **und** `appVersion`). Die Anwendung
   (API `/health`/OpenAPI und Web-Client) liest die Version zur Laufzeit aus den
   Paket-Metadaten (`procworks.__version__`) und zieht damit automatisch nach.
3. Gates lokal grün (`ruff check .`, `mypy src`, `pytest -q` in `core/`).
4. Release-Commit `chore(release): vX.Y.Z`.
5. Annotierten Tag setzen und mitschieben:
   `git tag -a vX.Y.Z -m "vX.Y.Z"` und `git push origin main --follow-tags`.
6. Workflow **Release** prüfen (Trivy grün, Images in ghcr.io). Anschließend
   die GitHub-Release-Notes aus dem passenden `CHANGELOG`-Abschnitt erzeugen.

## Sicherheitslücken

Sicherheitsrelevante Funde **nicht** als öffentliches Issue melden, sondern dem
Prozess in [SECURITY.md](SECURITY.md) folgen.

## Lizenz

Mit einem Beitrag stimmst du zu, dass dein Code unter der
**Business Source License 1.1 (BUSL-1.1)** des Projekts lizenziert wird (siehe
[LICENSE](LICENSE)).
