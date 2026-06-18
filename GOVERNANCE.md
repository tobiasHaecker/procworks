# Governance

ProcWorks wird derzeit als **maintainer-geführtes** Open-Source-Projekt
entwickelt.

## Rollen

- **Maintainer:** verantworten Roadmap, Reviews, Releases und die Durchsetzung
  des [Verhaltenskodex](CODE_OF_CONDUCT.md). Aktuelle Maintainer sind in
  [`.github/CODEOWNERS`](.github/CODEOWNERS) hinterlegt.
- **Mitwirkende:** alle, die über Issues und Pull Requests beitragen
  (siehe [CONTRIBUTING.md](CONTRIBUTING.md)).

## Entscheidungen

- Änderungen erfolgen über Pull Requests und benötigen die Freigabe eines
  Maintainers (gemäß `CODEOWNERS`).
- Bei Uneinigkeit entscheiden die Maintainer einvernehmlich; das Leitprinzip
  **Correctness by Construction** hat dabei Vorrang vor Bequemlichkeit.

## Releases

- **[Semantic Versioning](https://semver.org/)** und
  **[Conventional Commits](https://www.conventionalcommits.org/)**.
- Container-Images werden bei einem Versions-Tag (`v*`) automatisch gebaut,
  mit **Trivy** gescannt und nach **ghcr.io** veröffentlicht
  (siehe [`.github/workflows/release.yml`](.github/workflows/release.yml)).

## Lizenz

Das Projekt steht unter der **Business Source License 1.1** (siehe
[LICENSE](LICENSE)).
