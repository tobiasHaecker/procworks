# SPDX-License-Identifier: BUSL-1.1
"""Tests for the built-in demo data and the admin reset endpoint.

Covers the pure :func:`procworks.demo.load_demo` loader (org, two schemas, three
instances at different points, monitoring KPIs) and the ``POST /admin/reset``
maintenance endpoint that wipes the system to zero and optionally reloads the
demo -- including the RBAC gate and the login-preservation guarantee.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import procworks.api as api_module
from procworks import demo
from procworks.api import app
from procworks.audit import InMemoryAuditLog, compute_kpis, discover_process_map
from procworks.auth_password import (
    InMemoryCredentialStore,
    PasswordAuthBackend,
    User,
    hash_password,
)
from procworks.execution import ExecutionContext
from procworks.model import InstanceState, LifecycleState
from procworks.store import (
    InMemoryInstanceStore,
    InMemoryOrgStore,
    InMemorySchemaStore,
    hydrate_org,
    make_org_resolver,
    make_resolver,
)

client = TestClient(app)


# --- pure loader ----------------------------------------------------------


def _fresh_stores() -> tuple[
    InMemorySchemaStore, InMemoryInstanceStore, InMemoryOrgStore, InMemoryAuditLog
]:
    return (
        InMemorySchemaStore(),
        InMemoryInstanceStore(),
        InMemoryOrgStore(),
        InMemoryAuditLog(),
    )


def test_load_demo_builds_two_schemas_and_one_org() -> None:
    ss, ins, orgs, log = _fresh_stores()
    demo.load_demo(schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log)

    assert set(ss.list_ids()) == {demo.SCHEMA_URLAUB, demo.SCHEMA_BESCHAFFUNG}
    assert orgs.list_ids() == [demo.ORG_ID]

    org_resolver = make_org_resolver(orgs)
    urlaub = hydrate_org(ss.get(demo.SCHEMA_URLAUB), org_resolver)  # type: ignore[arg-type]
    beschaffung = ss.get(demo.SCHEMA_BESCHAFFUNG)
    assert urlaub.lifecycle_state is LifecycleState.RELEASED
    assert beschaffung is not None
    assert beschaffung.lifecycle_state is LifecycleState.ENTWURF
    # The released schema resolves its staffing against the shared org.
    assert urlaub.org_model_id == demo.ORG_ID
    assert "a-erika" in urlaub.org_model.agents


def test_load_demo_creates_three_instances_at_different_points() -> None:
    ss, ins, orgs, log = _fresh_stores()
    demo.load_demo(schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log)

    states = {iid: ins.get(iid).state for iid in ins.list_ids()}  # type: ignore[union-attr]
    assert len(states) == 3
    assert sum(s is InstanceState.RUNNING for s in states.values()) == 2
    assert sum(s is InstanceState.COMPLETED for s in states.values()) == 1
    # None of the demo instances is a throw-away test instance.
    assert all(not ins.get(iid).is_test for iid in ins.list_ids())  # type: ignore[union-attr]


def test_load_demo_feeds_monitoring_kpis_and_process_map() -> None:
    ss, ins, orgs, log = _fresh_stores()
    demo.load_demo(schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log)

    report = compute_kpis(log.list_all())
    assert report.total_instances == 3
    assert report.running == 2
    assert report.completed == 1
    pmap = discover_process_map(log.list_all())
    assert len(pmap.edges) >= 1


def test_load_demo_seeds_logins_only_with_password_backend() -> None:
    ss, ins, orgs, log = _fresh_stores()
    backend = PasswordAuthBackend(InMemoryCredentialStore())
    seeded = demo.load_demo(
        schema_store=ss,
        instance_store=ins,
        org_store=orgs,
        audit_log=log,
        password_backend=backend,
    )
    assert seeded == len(demo.DEMO_USERS)
    assert backend.store.get_user("erika.sander") is not None


def test_load_demo_is_idempotent_for_users() -> None:
    ss, ins, orgs, log = _fresh_stores()
    backend = PasswordAuthBackend(InMemoryCredentialStore())
    demo.load_demo(
        schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log,
        password_backend=backend,
    )
    # A second load over the same backend must not duplicate logins.
    again = demo.load_demo(
        schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log,
        password_backend=backend,
    )
    assert again == 0


# --- store clear ----------------------------------------------------------


def test_in_memory_stores_clear() -> None:
    ss, ins, orgs, log = _fresh_stores()
    demo.load_demo(schema_store=ss, instance_store=ins, org_store=orgs, audit_log=log)
    ss.clear()
    ins.clear()
    orgs.clear()
    log.clear()
    assert ss.list_ids() == []
    assert ins.list_ids() == []
    assert orgs.list_ids() == []
    assert log.list_all() == []


# --- admin reset endpoint -------------------------------------------------


@pytest.fixture
def clean_api() -> Iterator[None]:
    """Isolate the module-global stores so a reset never touches other tests."""

    saved = (
        api_module._store,
        api_module._instances,
        api_module._org_store,
        api_module._audit,
        api_module._resolver,
        api_module._org_resolver,
        api_module._context,
    )
    api_module._store = InMemorySchemaStore()
    api_module._instances = InMemoryInstanceStore()
    api_module._org_store = InMemoryOrgStore()
    api_module._audit = InMemoryAuditLog()
    api_module._resolver = make_resolver(api_module._store)
    api_module._org_resolver = make_org_resolver(api_module._org_store)
    api_module._context = ExecutionContext(api_module._resolver, api_module._instances)
    try:
        yield
    finally:
        (
            api_module._store,
            api_module._instances,
            api_module._org_store,
            api_module._audit,
            api_module._resolver,
            api_module._org_resolver,
            api_module._context,
        ) = saved


@pytest.fixture
def clean_password_api(clean_api: None) -> Iterator[PasswordAuthBackend]:
    """As ``clean_api`` but also swap in a fresh password backend with an admin."""

    original = api_module._auth_backend
    backend = PasswordAuthBackend(InMemoryCredentialStore())
    backend.store.put_user(
        User(
            login="admin",
            password_hash=hash_password("admin-pw1"),
            subject="admin",
            roles=frozenset({"admin"}),
            display_name="Ada Admin",
            must_change=False,
        )
    )
    api_module._auth_backend = backend
    try:
        yield backend
    finally:
        api_module._auth_backend = original


def test_admin_reset_loads_and_clears_demo(clean_api: None) -> None:
    # Open dev mode grants admin -> load the demo, then wipe to zero.
    loaded = client.post("/admin/reset", json={"load_demo": True})
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["demo_loaded"] is True
    assert body["schemas"] == 2
    assert body["instances"] == 3
    assert body["org_models"] == 1
    assert set(client.get("/schemas").json()) == {
        demo.SCHEMA_URLAUB,
        demo.SCHEMA_BESCHAFFUNG,
    }
    assert len(client.get("/instances").json()) == 3

    emptied = client.post("/admin/reset", json={"load_demo": False})
    assert emptied.status_code == 200
    empty_body = emptied.json()
    assert empty_body["schemas"] == 0
    assert empty_body["instances"] == 0
    assert empty_body["org_models"] == 0
    assert client.get("/schemas").json() == []


def _login(backend: PasswordAuthBackend, login: str) -> str:
    return backend.login(login, "admin-pw1").token


def test_admin_reset_requires_admin(clean_password_api: PasswordAuthBackend) -> None:
    backend = clean_password_api
    backend.store.put_user(
        User(
            login="vera.viewer",
            password_hash=hash_password("admin-pw1"),
            subject="vera.viewer",
            roles=frozenset({"viewer"}),
            must_change=False,
        )
    )
    token = backend.login("vera.viewer", "admin-pw1").token
    resp = client.post(
        "/admin/reset",
        json={"load_demo": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_reset_keeps_acting_admin_login(
    clean_password_api: PasswordAuthBackend,
) -> None:
    backend = clean_password_api
    backend.store.put_user(
        User(
            login="leftover.user",
            password_hash=hash_password("admin-pw1"),
            subject="leftover.user",
            roles=frozenset({"operator"}),
            must_change=False,
        )
    )
    token = _login(backend, "admin")
    resp = client.post(
        "/admin/reset",
        json={"load_demo": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # The acting admin survives; the unrelated login is wiped.
    assert backend.store.get_user("admin") is not None
    assert backend.store.get_user("leftover.user") is None
    # The admin's session is still valid afterwards.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_admin_reset_demo_seeds_usable_logins(
    clean_password_api: PasswordAuthBackend,
) -> None:
    backend = clean_password_api
    token = _login(backend, "admin")
    resp = client.post(
        "/admin/reset",
        json={"load_demo": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # The demo operator login works out of the box (no forced change).
    erika = backend.login("erika.sander", demo.DEMO_PASSWORD)
    assert "operator" in erika.principal.roles
    assert erika.principal.agent_id == "a-erika"
    # ... and she has an open task from the freshly loaded instances.
    tasks = client.get(
        "/me/tasks", headers={"Authorization": f"Bearer {erika.token}"}
    )
    assert tasks.status_code == 200
    assert len(tasks.json()) >= 1
