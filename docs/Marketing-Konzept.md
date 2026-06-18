# Marketing-Konzept – Kostenlose Bewerbung von ProcWorks

> Fokus: **Sichtbarkeit ohne Werbebudget** – organische Auffindbarkeit (SEO),
> Developer-/Open-Source-Kanäle und Community-Aufbau.
> Domain: **procworks.de** · Repo: github.com/tobiasHaecker/procworks
> © Tobias Häcker · Business Source License 1.1

## 1. Ziele

1. **Auffindbarkeit:** procworks.de rankt für die relevanten Suchbegriffe und
   wird von Suchmaschinen vollständig indexiert.
2. **Reichweite:** Die Zielgruppen stoßen über die Kanäle, die sie ohnehin
   nutzen (GitHub, Foren, Fachcommunities), auf ProcWorks.
3. **Vertrauen:** Klare Positionierung („Correctness by Construction") und
   hochwertige Inhalte statt Werbeversprechen.

**Erfolgsmessung (kostenlos):** Google Search Console (Impressionen, Klicks,
Position), GitHub-Stars/Forks/Traffic-Insights, Referrer-Statistiken.

## 2. Zielgruppen & Suchintention

| Zielgruppe                         | Sucht nach …                                            |
| ---------------------------------- | ------------------------------------------------------- |
| Entwickler / Architekt:innen       | „Workflow Engine open source", „BPM engine Python"      |
| Prozess-/BPM-Verantwortliche       | „Prozessmodellierung Software", „BPMN Tool kostenlos"   |
| Forschung / Lehre (ADEPT-Umfeld)   | „Correctness by Construction", „ADEPT Prozessmanagement"|
| Open-Source-Interessierte          | „self-hosted workflow", „process engine self hosted"    |

## 3. Keyword-Strategie

**Primäre Keywords** (Kern der Positionierung):
- Correctness by Construction
- Prozessmodellierung Open Source
- Workflow Engine (self-hosted / Python)

**Sekundäre / Long-Tail-Keywords** (geringerer Wettbewerb, hohe Passung):
- „korrekte Prozessmodelle per Konstruktion"
- „BPMN Workflow Engine selbst hosten"
- „ADEPT Prozessmanagement Open Source"
- „validate before commit Prozess-Engine"
- „block-strukturierte Prozessmodellierung"

> Empfehlung: Pro Keyword-Cluster **eine eigene Inhaltsseite** (siehe Abschnitt 6).
> Long-Tail zuerst – dort sind schnelle Rankings am wahrscheinlichsten.

## 4. Technisches SEO (bereits umgesetzt)

Auf der Website sind folgende Grundlagen bereits enthalten:

- **Sprechender `<title>` + Meta-Description** mit Kernbotschaft.
- **Canonical-URL** (`https://procworks.de/`) gegen Duplicate Content.
- **Open-Graph- und Twitter-Card-Tags** für ansprechende Link-Vorschauen.
- **Strukturierte Daten (JSON-LD, `SoftwareApplication`)** für Rich Results.
- **`robots.txt`** (Indexierung erlaubt, Verweis auf Sitemap).
- **`sitemap.xml`** mit der Startseite.
- **Semantisches HTML** (eine `h1`, klare `h2`/`h3`-Hierarchie), responsiv,
  schnelle Ladezeit (kein Build, kein JS-Framework).

**Noch zu tun nach dem Go-Live:**

1. **Google Search Console** einrichten: Domain `procworks.de` verifizieren
   (DNS-TXT-Record bei IONOS), Sitemap `https://procworks.de/sitemap.xml`
   einreichen, Indexierung der Startseite anfordern.
2. **Bing Webmaster Tools** analog einrichten (deckt Bing/DuckDuckGo ab).
3. **HTTPS + www-Weiterleitung** prüfen (eine kanonische Variante).
4. **PageSpeed/Core Web Vitals** mit PageSpeed Insights gegenprüfen.
5. Optional ein **OG-Vorschaubild** (`og:image`, 1200×630 px) ergänzen –
   verbessert Klickraten beim Teilen.

## 5. Off-Page-SEO (Backlinks – kostenlos)

Hochwertige, thematisch passende Backlinks sind der stärkste organische Hebel:

- **GitHub-Repo** mit aussagekräftiger README, Topics/Tags und Link auf
  procworks.de (Repo-Website-Feld setzen).
- **Awesome-Listen** (Pull Requests): z. B. „awesome-workflow-engines",
  „awesome-bpm", „awesome-selfhosted" – Eintrag mit kurzer Beschreibung.
- **Verzeichnisse/Listings** (siehe Abschnitt 8): jeweils mit Backlink.
- **Wikipedia/Fachwikis:** nur als Quelle/Einzelnachweis, wenn inhaltlich
  passend und regelkonform (kein Spam).
- **Gastbeiträge / Erwähnungen** in Dev-Blogs und Newslettern.

## 6. Content-Marketing (organischer Langzeit-Hebel)

Eigene Inhalte ziehen kontinuierlich Suchtraffic. Pragmatisch starten:

- **Doku als SEO-Asset:** Das Architektur-Konzept und ein Quickstart sind
  bereits Inhalte – öffentlich und verlinkbar machen (GitHub Pages / Repo).
- **Artikel-Ideen** (je 1 Keyword-Cluster):
  - „Was bedeutet Correctness by Construction in der Prozessmodellierung?"
  - „Warum klassische BPMN-Tools fehlerhafte Modelle zulassen – und wie es anders geht"
  - „Self-hosted Workflow Engine mit Docker in 10 Minuten"
  - „ADEPT verständlich erklärt: stabile Prozessänderungen zur Laufzeit"
- **Format:** problemorientiert, mit Codebeispielen und einem klaren CTA
  (GitHub-Stern / Repo ansehen).
- **Cross-Posting:** Artikel zuerst auf der eigenen Domain (Canonical),
  danach gespiegelt auf dev.to / Medium / Hashnode mit `rel=canonical`
  zurück auf procworks.de.

## 7. Developer- & Open-Source-Kanäle (Reichweite, kostenlos)

| Kanal                         | Vorgehen                                                       |
| ----------------------------- | ------------------------------------------------------------- |
| **GitHub**                    | Topics, README-Badges, Releases, „Show off" in Discussions    |
| **Hacker News** („Show HN")   | Ein gut getimter Launch-Post mit ehrlicher Beschreibung       |
| **Reddit**                    | r/selfhosted, r/opensource, r/bpmn, r/programming (Regeln!)   |
| **Lobsters / Dev.to**         | Technische Artikel + Projektvorstellung                       |
| **Mastodon (Fediverse)**      | #opensource #selfhosted #BPM – authentische Updates           |
| **Stack Overflow**            | Fragen zum Thema fachlich beantworten, dezent verweisen       |

> Wichtig: In Communities **zuerst Mehrwert liefern**, nicht plump bewerben.
> Ein ehrlicher „Ich habe X gebaut, Feedback willkommen"-Post wirkt am besten.

## 8. Verzeichnisse & Plattformen (Listings mit Backlink)

- **Product Hunt** – Launch als Open-Source-Tool.
- **AlternativeTo** – als Alternative zu kommerziellen BPM-/Workflow-Tools.
- **OpenHub / Libraries.io** – automatisch über das Repo.
- **awesome-selfhosted / awesome-workflow-engines** (PRs, vgl. Abschnitt 5).
- **G2 / Capterra** (Free-Listing, optional) – für BPM-Software-Suchen.
- **Open-Source-Newsletter** (z. B. „Console", „Changelog") – Einreichung.

## 9. Social & Fachcommunities

- **LinkedIn:** Persönliches Profil + ggf. ProcWorks-Seite; Beiträge zu
  Prozess-/Korrektheits-Themen, in passenden BPM-Gruppen teilen.
- **X / Bluesky:** kurze Updates, Release-Ankündigungen, #BPM #OpenSource.
- **YouTube (optional):** kurzer Screencast „ProcWorks in 3 Minuten" –
  Video rankt zusätzlich in der Such- und Videosuche.
- **BPM-Fachforen / Xing-Gruppen (DACH):** fachlicher Austausch.

## 10. Akademischer Hebel (Alleinstellung)

ProcWorks basiert auf der Forschungsidee **ADEPT2 (Universität Ulm)**. Das ist
ein glaubwürdiges Differenzierungsmerkmal:

- Bezug auf die Forschung in Inhalten klar benennen (mit Quellenangabe).
- Kontakt zu Lehrstühlen / Forschungsgruppen im BPM-Umfeld suchen
  (Lehre/Demonstrator-Nutzung) – kann zu hochwertigen `.edu`/`.uni`-Backlinks
  und Erwähnungen führen.

## 11. Fahrplan & Priorisierung

**Phase 1 – Fundament (sofort, höchster Hebel):**
1. Website live unter procworks.de (HTTPS, www-Redirect).
2. Search Console + Bing Webmaster Tools verifizieren, Sitemap einreichen.
3. GitHub-README/Topics/Website-Feld optimieren, Backlink zur Domain setzen.

**Phase 2 – Reichweite (Wochen):**
4. „Show HN" / Reddit-/Dev.to-Vorstellung mit ehrlichem Pitch.
5. Einträge in 2–3 Awesome-Listen + AlternativeTo + Product Hunt.
6. Erster Fachartikel (Long-Tail-Keyword) auf der Domain, gespiegelt auf dev.to.

**Phase 3 – Stetiges Wachstum (laufend):**
7. Regelmäßige Artikel/Release-Posts (1×/Monat genügt).
8. Community-Präsenz (Foren, Mastodon, LinkedIn) pflegen.
9. Rankings in der Search Console beobachten und Inhalte nachschärfen.

## 12. Leitplanken

- **Kein Spam:** Plattform-Regeln respektieren, Mehrwert vor Eigenwerbung.
- **Konsistente Botschaft:** überall dieselbe Kernaussage und Domain.
- **Ehrlichkeit:** Open-Source-Status, Lizenz (BUSL-1.1) und Reifegrad
  transparent kommunizieren – schafft Vertrauen in der Dev-Community.
