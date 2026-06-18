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
- **[Semantic Versioning](https://semver.org/)** für Releases.
- Arbeite auf einem Feature-Branch und stelle einen Pull Request gegen `main`.

## Pull Requests

1. Halte den PR fokussiert (eine logische Änderung).
2. Beschreibe **Was** und **Warum**; verlinke zugehörige Issues.
3. Stelle sicher, dass CI grün ist (Lint, Typen, Tests).
4. Aktualisiere Doku/`CHANGELOG`, wenn sich Verhalten oder API ändern.

## Sicherheitslücken

Sicherheitsrelevante Funde **nicht** als öffentliches Issue melden, sondern dem
Prozess in [SECURITY.md](SECURITY.md) folgen.

## Lizenz

Mit einem Beitrag stimmst du zu, dass dein Code unter der
**Business Source License 1.1 (BUSL-1.1)** des Projekts lizenziert wird (siehe
[LICENSE](LICENSE)).
