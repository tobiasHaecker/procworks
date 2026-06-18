# Auth-Konzept – Variante C: Pluggable AuthBackend

> Status: **Entwurf für die spätere Umsetzung**
> Betrifft: `core/src/procworks/api.py` (einziger Boundary), neues Modul `core/src/procworks/auth.py`
> Lizenz/Eigentümer: © Tobias Häcker · Business Source License 1.1

## 1. Ziel & Motivation

Der ProcWorks-Kernel ist heute **headless und vollständig unauthentifiziert**.
Jeder, der die API erreicht, kann jede Operation ausführen – inklusive
Modellierung, Freigabe und Ausführung im Namen beliebiger Bearbeiter.

Zwei konkrete Schwachstellen sollen geschlossen werden:

1. **Fehlende Authentifizierung** – die API hat keine Identitätsprüfung
   (`CORS allow_origins=["*"]`, keine Tokens, kein Login).
2. **Impersonation über den Request-Body** – die Endpunkte
   `POST /instances/{id}/complete` und `POST /instances/{id}/decide` übernehmen
   die handelnde Identität aus dem Request (`req.agent_id`). Ein Client kann sich
   damit als beliebiger Bearbeiter ausgeben. Das untergräbt die
   BZR-Berechtigungsprüfung (`assignment.py`, `eligible_agents`) und die
   Aussagekraft des Audit-Logs.

> **Architektur-Leitplanke:** Die Korrektheitslogik bleibt im Kern (z. B. die
> feingranulare BZR-Eignungsprüfung). Auth ist eine **zusätzliche, grobe
> Schutzschicht am API-Boundary** und ersetzt die Kernprüfungen nicht.

## 2. Variante C im Überblick

Variante C führt einen **austauschbaren `AuthBackend`** ein – analog zum
bestehenden `SchemaStore`/`InstanceStore`-Protokoll-Muster und der
umgebungsbasierten Factory (`create_store()` liest `DATABASE_URL`).

```
                ┌────────────────────────────────────────────┐
   HTTP Request │  FastAPI-Endpunkt (api.py)                 │
   + Auth-Header│                                            │
  ──────────────▶  Depends(get_principal)                    │
                │        │                                   │
                │        ▼                                   │
                │   AuthBackend.authenticate(request)        │  ← austauschbar
                │        │  -> Principal{agent_id, roles}     │
                │        ▼                                   │
                │   require_role("operator")  (optional)     │  ← grobe RBAC
                │        │                                   │
                │        ▼                                   │
                │   exe.complete_activity(..., agent_id=      │
                │        principal.agent_id)                 │  ← NICHT aus Body
                │        │                                   │
                │        ▼                                   │
                │   Kern: BZR-Eignungsprüfung (409 wenn nein) │  ← bleibt im Kern
                └────────────────────────────────────────────┘
```

Kernpunkte:

- **Ein Protokoll, mehrere Implementierungen.** `AuthBackend` ist ein
  `typing.Protocol`. Die erste konkrete Implementierung ist ein einfaches
  **Token-Backend**; JWT/OIDC sind später ohne API-Änderung ergänzbar.
- **Default = offener Dev-Modus.** Ohne Konfiguration verhält sich die API wie
  heute (Quickstart, lokale Tests, Prototyp bleiben unverändert lauffähig).
- **Identität kommt aus dem `Principal`, nicht aus dem Body.** Damit ist die
  Impersonation-Lücke strukturell geschlossen.

## 3. Bausteine

### 3.1 `Principal`

Die geprüfte, serverseitig ermittelte Identität eines Requests.

```python
class Principal(BaseModel):
    agent_id: str | None      # verknüpfter Bearbeiter (für /complete, /decide)
    subject: str              # stabile Identität des Aufrufers (z. B. Token-sub)
    roles: frozenset[str]     # grobe RBAC-Rollen (siehe 3.4)
    display_name: str | None = None
```

- `agent_id` bindet den Aufrufer an einen ProcWorks-Bearbeiter. Nur diese ID
  wird an `exe.complete_activity(...)` / `exe.decide_branch(...)` übergeben.
- `roles` steuert die **grobe** Zugriffskontrolle am Boundary (orthogonal zur
  feingranularen BZR-Prüfung im Kern).

### 3.2 `AuthBackend` (Protocol)

```python
class AuthBackend(Protocol):
    def authenticate(self, request: Request) -> Principal:
        """Leitet eine geprüfte Principal aus dem Request ab.

        Wirft AuthError(401), wenn keine gültige Identität feststellbar ist.
        """
        ...
```

Vorgesehene Implementierungen:

| Backend            | Zweck                                   | Konfiguration                          |
| ------------------ | --------------------------------------- | -------------------------------------- |
| `OpenAuthBackend`  | Dev/Default: anonymer Admin-Principal   | keine                                  |
| `TokenAuthBackend` | Erstes produktives Backend (statisch)   | `PROCWORKS_AUTH=token` + Token-Tabelle |
| `JwtAuthBackend`   | Später: JWT/OIDC-Validierung            | Issuer/JWKS-URL/Audience               |

> Das `OpenAuthBackend` liefert einen Principal mit allen Rollen und ohne
> festes `agent_id`. Für `/complete` und `/decide` muss der Aufrufer im
> Dev-Modus weiterhin einen `agent_id` benennen (siehe 5) – die Kern-BZR-Prüfung
> bleibt aktiv und schützt die Korrektheit auch ohne Auth.

### 3.3 Factory (umgebungsbasiert)

Analog zu `create_store()`:

```python
def create_auth_backend() -> AuthBackend:
    mode = os.environ.get("PROCWORKS_AUTH", "open").lower()
    if mode == "token":
        from procworks.auth_token import TokenAuthBackend
        return TokenAuthBackend.from_env()
    if mode == "jwt":
        from procworks.auth_jwt import JwtAuthBackend
        return JwtAuthBackend.from_env()
    return OpenAuthBackend()
```

- Default `open` → keine Verhaltensänderung gegenüber heute.
- Lazy Imports halten den Dev-/In-Memory-Pfad frei von zusätzlichen
  Abhängigkeiten (gleiches Muster wie der SQLAlchemy-Import in `store.py`).

### 3.4 Grobe RBAC-Rollen am Boundary

Vier grobe Rollen, die die feingranulare BZR-Logik **ergänzen**, nicht ersetzen:

| Rolle      | Darf (grob)                                                        |
| ---------- | ----------------------------------------------------------------- |
| `admin`    | alles (Org-/Connector-/Template-Verwaltung)                       |
| `modeler`  | Schemata erstellen/ändern, Operationen, Freigabe                  |
| `operator` | Instanzen starten, Aktivitäten abschließen, Verzweigungen wählen  |
| `viewer`   | nur lesend: Schemata, Instanzen, Aufgaben, Monitoring/KPIs        |

Durchsetzung über einen Dependency-Factory:

```python
def require_role(*allowed: str) -> Callable[[Principal], Principal]:
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="forbidden")
        return principal
    return _dep
```

## 4. Einbindung in FastAPI

Eine zentrale Dependency liefert den `Principal`; der gewählte Backend wird
einmalig beim App-Start gebaut (wie `_store`, `_instances`).

```python
# auth.py
_auth_backend = create_auth_backend()

def get_principal(request: Request) -> Principal:
    return _auth_backend.authenticate(request)   # AuthError -> 401
```

Endpunkte deklarieren ihre nötige Rolle:

```python
@app.post("/instances/{instance_id}/start")
def post_start_instance(..., principal: Principal = Depends(require_role("operator", "admin"))):
    ...

@app.get("/instances/{instance_id}")
def get_instance(..., principal: Principal = Depends(require_role("viewer", "operator", "modeler", "admin"))):
    ...
```

## 5. Schließen der Impersonation-Lücke

Die handelnde Identität wird **nicht mehr aus dem Body** gelesen, sondern aus
dem `Principal` abgeleitet.

Heute (verwundbar):

```python
@app.post("/instances/{instance_id}/complete", response_model=ProcessInstance)
def post_complete_activity(instance_id: str, req: CompleteActivityRequest):
    ...
    exe.complete_activity(before, schema, req.node_id, req.data,
                          agent_id=req.agent_id, context=_context)   # ⚠ aus Body
    _audit.append(..., agent_id=req.agent_id)                        # ⚠ fälschbar
```

Künftig (Variante C):

```python
@app.post("/instances/{instance_id}/complete", response_model=ProcessInstance)
def post_complete_activity(
    instance_id: str,
    req: CompleteActivityRequest,
    principal: Principal = Depends(require_role("operator", "admin")),
):
    acting_agent = _resolve_acting_agent(principal, req.agent_id)
    ...
    exe.complete_activity(before, schema, req.node_id, req.data,
                          agent_id=acting_agent, context=_context)
    _audit.append(..., agent_id=acting_agent)
```

Regel in `_resolve_acting_agent(principal, requested)`:

- **Backend mit fester Bindung** (Token/JWT): `principal.agent_id` ist
  verbindlich. Ein abweichendes `req.agent_id` wird ignoriert oder mit `403`
  abgelehnt (kein Handeln im fremden Namen).
- **Open/Dev-Backend** (kein `agent_id` im Principal): `req.agent_id` wird
  übernommen, damit lokale Tests und der Quickstart unverändert funktionieren.
  Die Korrektheit bleibt durch die **BZR-Eignungsprüfung im Kern** geschützt
  (unzulässiger Bearbeiter → `409`).

Betroffene Endpunkte: `POST /instances/{id}/complete`,
`POST /instances/{id}/decide` (sowie `start`, falls dort eine Startidentität
relevant wird).

## 6. Konfiguration

| Variable            | Werte                         | Wirkung                                       |
| ------------------- | ----------------------------- | --------------------------------------------- |
| `PROCWORKS_AUTH`    | `open` (Default), `token`, `jwt` | Auswahl des AuthBackends                    |
| `PROCWORKS_TOKENS`  | Pfad/URL/Connection            | Tokenquelle für `TokenAuthBackend`           |
| (JWT, später)       | Issuer, JWKS-URL, Audience     | Validierungsparameter für `JwtAuthBackend`   |

Vorgaben:

- **Lokal/Dev/Tests:** keine Variable gesetzt → `open` → unverändertes Verhalten.
- **Produktion:** `PROCWORKS_AUTH=token` (oder `jwt`); zusätzlich **CORS
  härten** (`allow_origins` auf konkrete Frontend-Origin statt `*`).

## 7. CORS-Härtung (begleitend)

Mit aktiver Auth sollte die heutige `allow_origins=["*"]`-Policy ebenfalls
konfigurierbar werden, z. B. über `PROCWORKS_CORS_ORIGINS` (kommaseparierte
Liste). Default bleibt offen für den lokalen Kernel; Produktion setzt konkrete
Origins.

## 8. Teststrategie

Neues Modul `core/tests/test_auth.py`:

- **Default offen:** ohne `PROCWORKS_AUTH` verhalten sich alle bestehenden
  Endpunkte wie bisher (Regression gegen die vorhandene Suite).
- **Token-Backend:** gültiges Token → `200`; fehlendes/ungültiges → `401`.
- **RBAC:** `viewer` auf Schreib-Endpunkt → `403`; `operator` erlaubt.
- **Impersonation blockiert:** Mit Token-Backend wird `req.agent_id ≠
  principal.agent_id` ignoriert/`403`; Audit-Event trägt die echte Identität.
- **Kern-BZR unverändert:** nicht eignungsberechtigter Bearbeiter → weiterhin
  `409` aus dem Kern.

## 9. Umsetzungsschritte (für später)

1. `core/src/procworks/auth.py`: `Principal`, `AuthError`, `AuthBackend`-Protocol,
   `OpenAuthBackend`, `get_principal`, `require_role`, `create_auth_backend`.
2. `core/src/procworks/auth_token.py`: `TokenAuthBackend.from_env()`.
3. `api.py`: Dependencies an den Endpunkten ergänzen; `_resolve_acting_agent`
   einführen; `agent_id` in `/complete` und `/decide` aus dem `Principal` ziehen.
4. CORS konfigurierbar machen (`PROCWORKS_CORS_ORIGINS`).
5. `core/tests/test_auth.py` ergänzen; `ruff`/`mypy`/`pytest` grün halten.
6. Doku/`README.md` und `SECURITY.md` um die Auth-Konfiguration ergänzen.

## 10. Nicht-Ziele

- Kein Benutzer-Management-UI und kein Passwort-Login im Kern (Identitäten
  kommen vom Token/IdP).
- Keine Verlagerung von Korrektheitslogik in die Auth-Schicht – BZR-Eignung
  und Validierung bleiben im Kern (`validate-before-commit`).
