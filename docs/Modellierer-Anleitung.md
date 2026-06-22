<!-- SPDX-License-Identifier: BUSL-1.1 -->
# ProcWorks – Anleitung für Modellierer (Prozesse erstellen und freigeben)

Diese Anleitung richtet sich an **Modellierer** (Rolle `modeler` oder
`admin`), die einen Prozess von Grund auf erstellen, mit Daten und Bearbeitern
verdrahten, testen und freigeben. Sie führt Schritt für Schritt durch alle dafür
nötigen Sichten des Web-Clients.

> Grundprinzip **Correctness by Construction (CbC):** Das Werkzeug bietet nur
> Änderungen an, die das Modell korrekt halten. Einen „Validieren"-Knopf gibt es
> bewusst nicht – Korrektheit ist ein *Zustand*, kein nachträglicher Prüflauf.
> Unzulässiges weist der Kern ab; das bestehende Modell bleibt dabei unverändert.

> ⚠️ **Hinweis zur Haftung.** ProcWorks wird ohne jede Gewährleistung und – soweit
> gesetzlich zulässig – **ohne jede Haftung** bereitgestellt; die Nutzung erfolgt
> auf eigenes Risiko. Details: [DISCLAIMER.md](../DISCLAIMER.md).

---

## 0. Überblick: die zwei Korrektheitsstufen

ProcWorks trennt zwei Stufen – das erklärt, warum man jederzeit weitermodellieren
kann, aber erst am Ende freigeben darf:

| Stufe | Was sie sichert | Wann erzwungen |
|-------|------------------|----------------|
| **(A) Struktur** | Blockstruktur, Erreichbarkeit, Datenfluss (K-, D-, C-, Z-, A-Regeln) | **bei jeder Operation** – immer erfüllt |
| **(B) Release-Reife** | jeder Schritt hat einen Dienst, jeder interaktive Schritt einen Bearbeiter, alle Pflichtdaten sind versorgt (B1–B3) | **spätestens bei der Freigabe** |

Ein halbfertiges Modell ist strukturell **immer** korrekt, aber noch nicht
ausführbar. Die Freigabe (`RELEASED`) wird so lange blockiert, bis auch Stufe B
vollständig erfüllt ist. Die noch offenen Punkte zeigt die **Befunde-Liste** in
der Modellieren-Sicht laufend an.

---

## 1. Neues Schema anlegen

1. Sicht **Modellieren** öffnen (links in der Navigation).
2. Oben rechts auf **„+ Neu"** klicken, einen sprechenden Namen vergeben
   (z. B. *Urlaubsantrag*) und bestätigen.
3. Es entsteht ein Schema im Zustand **ENTWURF** mit einem START- und einem
   END-Knoten. Nur ein Entwurf ist editierbar.

> Alternativ: **„BPMN-Import"** liest eine BPMN-2.0-Datei ein. Nicht regelkonforme
> Konstrukte (z. B. unstrukturierte OR-Gateways) werden abgelehnt oder zur
> manuellen Auflösung markiert – nie als inkorrektes Modell gespeichert.

---

## 2. Schritte einfügen (geführtes Modellieren)

Im Kontrollfluss-Diagramm sitzt an jeder Kante ein **„+"**. Ein Klick darauf
öffnet den Einfüge-Dialog mit drei Mustern:

| Muster | Bedeutung | Ergebnis |
|--------|-----------|----------|
| **Seriell** | ein Schritt nach dem anderen | eine neue Aktivität in der Reihe |
| **Parallel (UND)** | mehrere Zweige laufen gleichzeitig | AND-Split **mit** zugehörigem AND-Join |
| **Bedingt (XOR)** | genau ein Zweig wird gewählt | XOR-Split **mit** zugehörigem XOR-Join, je Zweig eine Bedingung |

**Wichtig:** Verzweigungen werden immer als **vollständiger, symmetrischer Block**
erzeugt – ein Split bringt seinen Join automatisch mit (Blockstruktur, K1). Das
freie Ziehen von Kanten gibt es bewusst nicht.

**Praxis-Tipp (Benennung):** Aktivitäten als „Objekt + Verb" benennen
(*„Antrag prüfen"*, *„Bestellung freigeben"*). Das verbessert die Lesbarkeit und
folgt den anerkannten Modellierungsrichtlinien (7PMG).

### Schritte umbenennen oder entfernen

- Einen Knoten **anklicken** → der **Knoten-Inspektor** (rechte Spalte) erlaubt
  Umbenennen und Entfernen.
- Eine **Verzweigung** wird über ihren öffnenden **Split** entfernt (der ganze
  Block inkl. Join verschwindet). Join-Knoten lassen sich nicht einzeln löschen.
- Beim Entfernen werden abhängige Bindungen (Daten, Dienste, Bearbeiterregeln)
  automatisch mit bereinigt – es entstehen keine verwaisten Verweise.

---

## 3. Daten verdrahten (Datensicht)

Aktivitäten kommunizieren über **Datenelemente** (Prozessvariablen), nicht über
versteckte Kanäle. Das geschieht in der Sicht **Datensicht**.

1. **Datenelement anlegen:** **„+ Datenelement"** → Name und Typ wählen
   (`Integer`, `Float`, `String`, `Date`, `Boolean`, `URI`).
2. **Schreiben/Lesen verbinden:** je Aktivität festlegen, welche Elemente sie
   **schreibt** und welche sie **liest**.

**Die goldene Datenfluss-Regel (D1):** Ein Pflicht-Eingabeparameter muss auf
**allen** Pfaden, die zu der lesenden Aktivität führen, vorher **geschrieben**
worden sein. Andernfalls lehnt der Kern die Lesebindung ab.

- In **XOR-Zweigen** zählt nur, was in **allen** Zweigen geschrieben wird (der
  Join bildet die Schnittmenge). Wer ein Element hinter dem Join verpflichtend
  lesen will, muss es **in jedem** Zweig schreiben.
- In **parallelen (UND-)Zweigen** stehen hinter dem Join die Schreibvorgänge
  **aller** Zweige zur Verfügung – aber zwei Zweige dürfen nicht **dasselbe**
  Element gleichzeitig schreiben (D2).
- Reihenfolge beim Bauen: erst **schreiben**, dann **lesen** – jede Bindung wird
  sofort geprüft; ein Lesen ohne vorhandenen Schreiber würde abgelehnt.

> **Externe Daten** (Direktzugriff auf eine Datenbank) werden in der Sicht
> **Integration** angebunden (Connector + Entität + Schlüsselelement). Siehe
> [Integrations-Leitfaden.md](Integrations-Leitfaden.md).

---

## 4. Organisation und Bearbeiter (Ressourcensicht)

Wer einen interaktiven Schritt bearbeiten darf, ergibt sich aus dem
**Organisationsmodell** und einer **Bearbeiterzuordnungsregel (BZR)** je Schritt.

1. **Organisation modellieren** (Sicht **Ressourcensicht**):
   - **„+ Rolle"** (z. B. *Sachbearbeiter*, *Leitung*),
   - Organisationseinheiten,
   - **„+ Agent"** (die konkreten Personen) und ihre Rollen/Einheiten.
   - Rechts unter **„Ressourcen-Befunde"** stellt ein **Organigramm** die
     Abteilungs-Hierarchie (mit Vorgesetztem und Agenten-Anzahl je Einheit) dar.
     Ein **Klick auf eine Abteilung** hebt sie samt ihrer Agenten – inklusive
     Vorgesetztem – in der Agentenliste hervor; ein Klick auf das ★-Badge eines
     Vorgesetzten im Bereich **„Abteilungen"** hebt diesen gezielt hervor.
2. **Bearbeiterregel je Schritt** festlegen (Tabelle *Schritt → Bearbeiterregel*):
   z. B. „Rolle = Sachbearbeiter". Die Regelsprache kennt `AND`/`OR`/`EXCEPT`,
   Modifikatoren `*`/`+` und Rückbezüge wie `NodePerformingAgent(nodeId)`.

**Korrektheitsregeln dahinter:**

- **Z1** – die Regel ist syntaktisch gültig und referenziert nur existierende
  Rollen/Einheiten.
- **Z2** – die Regel ist **erfüllbar**: sie muss mindestens einen Agenten liefern
  (eine Rolle ohne Träger ist eine gemeldete Inkonsistenz).
- **Z3** – ein `NodePerformingAgent(x)`-Bezug verweist nur auf Schritte, die
  garantiert **vorher** laufen.
- **Automatische** Schritte brauchen keine BZR, **interaktive** schon (Z4).

> **Geteilte Organisation:** Ein Organisationsmodell kann einmal angelegt und in
> mehreren Schemata wiederverwendet werden (verknüpfen/lösen über das
> Organisations-Banner). Verknüpfte Organisationen bleiben auch nach der Freigabe
> editierbar; Bearbeiterregeln bleiben Entwurf-gebunden.

---

## 5. Dienste & Automatik (optional)

- **Manuell/interaktiv** (Standard): ein Mensch erledigt den Schritt über
  „Meine Aufgaben".
- **Automatisch:** in der Sicht **Integration** lässt sich einer Aktivität eine
  **Automatik** zuweisen – als External-Task (ein externer Worker holt und
  erledigt die Aufgabe) oder als HTTP-Push (ProcWorks ruft ein Zielsystem auf).
  Details: [Integrations-Leitfaden.md](Integrations-Leitfaden.md).

Die Regeln **A1–A3** prüfen, dass ein zugeordneter Dienst (Template) typkonform
an die Datenelemente gebunden ist; **I1–I4** prüfen die Wohlgeformtheit der
Automatik-Bindung.

---

## 6. Fortschritt prüfen: Befunde & Revision

In der Modellieren-Sicht zeigt die rechte Spalte laufend:

- **Befunde-Liste:** alle noch offenen Punkte mit **Regel-Code** und betroffenem
  Knoten (z. B. `B2: Schritt ohne Bearbeiter [n3]`). Solange hier Stufe-B-Punkte
  stehen, ist die Freigabe blockiert. Eine Erläuterung aller Codes findet sich
  in der **In-App-Sicht „Hilfe"** und in [Architektur-Konzept-Prozessmodellierung.md](Architektur-Konzept-Prozessmodellierung.md) §3.
- **Revision:** erzeugt aus einem freigegebenen Schema eine neue, editierbare
  Version (siehe §9).

---

## 7. Testlauf vor der Freigabe

Als Modellierer dürfen Sie einen **Entwurf** als **Test-Instanz** starten, ohne
ihn freizugeben:

1. Sicht **Ausführung** öffnen.
2. Bei einem nicht freigegebenen Schema erscheint **„▶ Test-Instanz starten"**.
3. Die Test-Instanz trägt eine **TEST**-Markierung und wird **nicht** ins
   Monitoring/KPIs gezählt – ideal, um den eigenen Entwurf durchzuspielen.

So lässt sich der Ablauf inkl. Datenerfassung und XOR-Entscheidungen prüfen,
bevor echte Instanzen laufen.

---

## 8. Freigeben (RELEASED)

1. Sind alle Befunde behoben (Stufe A **und** B erfüllt), erscheint in der
   Modellieren-Sicht der Button **„Freigeben"**.
2. Nach der Freigabe ist das Schema **unveränderlich** (`RELEASED`) und kann
   instanziiert werden – Bearbeiter sehen ab jetzt echte Aufgaben.

> Erst ein freigegebenes Schema lässt sich von Bearbeitern produktiv nutzen. Die
> Vorbereitung der Logins beschreibt die [Mitarbeiter-Anleitung.md](Mitarbeiter-Anleitung.md).

---

## 9. Ändern nach der Freigabe: Revisionen

Ein freigegebenes Schema wird **nicht** direkt geändert. Stattdessen:

1. Eine **Revision** erzeugen (rechte Spalte in der Modellieren-Sicht bzw. aus
   der Ausführungs-/Monitoring-Sicht). Die Revision trägt **denselben Namen**,
   aber eine **neue ID** und eine **erhöhte Version** (z. B. *Urlaubsantrag (v2)*).
2. Die Revision wie gewohnt bearbeiten und erneut freigeben.
3. **Laufende Instanzen** können – sofern verträglich – kontrolliert auf die neue
   Version **migriert** werden (Kriterien M1–M5). Unverträgliche Instanzen laufen
   sicher auf der alten Version weiter; sie werden nie in einen Mischzustand
   gezwungen.

---

## 10. Häufige Befunde und was zu tun ist

| Code | Bedeutung | Lösung |
|------|-----------|--------|
| **B1** | Schritt ohne Dienst | Dienst/Template zuweisen oder Schritt als manuell belassen |
| **B2** | interaktiver Schritt ohne Bearbeiter | Bearbeiterregel in der Ressourcensicht setzen |
| **B3** | Pflichtdaten nicht versorgt | fehlendes Datenelement vorher schreiben lassen |
| **D1** | Lesen vor Schreiben | Element auf **allen** Pfaden vor dem Lesen schreiben |
| **D2** | konkurrierende Schreibzugriffe | nicht zwei Parallelzweige dasselbe Element schreiben lassen |
| **D3** | Typkonflikt | Typen von Quelle und Senke angleichen |
| **Z2** | Bearbeiterregel liefert niemanden | Rolle mit Trägern hinterlegen oder Regel anpassen |

Die vollständige Liste aller Regel-Codes erklärt die **In-App-Hilfe** (Sicht
„Hilfe") und §3 des [Architektur-Konzepts](Architektur-Konzept-Prozessmodellierung.md).

---

## Kurzreferenz: der typische Weg

1. **Modellieren** → „+ Neu" → Schritte über „+" einfügen (seriell/parallel/bedingt).
2. **Datensicht** → Datenelemente anlegen → schreiben/lesen verbinden.
3. **Ressourcensicht** → Rollen/Agenten anlegen → Bearbeiterregeln je Schritt.
4. (optional) **Integration** → Automatik/externe Daten.
5. **Ausführung** → Test-Instanz starten und durchspielen.
6. **Modellieren** → alle Befunde lösen → **Freigeben**.
7. Bei Änderungswunsch → **Revision** → bearbeiten → freigeben → ggf. migrieren.
