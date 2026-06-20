# SPDX-License-Identifier: BUSL-1.1
"""Built-in demo data set and the one-shot loader behind the admin reset.

A fresh kernel is empty, which makes it hard to grasp what the tool can do. The
:func:`load_demo` loader populates the stores with a small but complete world so
every view has something to show: one shared organisation, two example
processes (one *released*, one *draft*), three running/finished instances at
different points, process variables and -- in password mode -- a handful of
ready-to-use logins.

The data is built exclusively through the public operations (the same
validate-before-commit path every client uses), so the demo can never create an
incorrect schema. Loading is wired to ``POST /admin/reset`` (admin only); the
same endpoint also wipes everything back to an empty system.
"""

from __future__ import annotations

from procworks import execution as exe
from procworks import operations as ops
from procworks import org as org_ops
from procworks.audit import AuditLog, EventType
from procworks.auth_password import (
    PasswordAuthBackend,
    User,
    hash_password,
)
from procworks.model import (
    AccessMode,
    DataType,
    InstanceState,
    NodeType,
    OrgModel,
    ProcessInstance,
    ProcessSchema,
    StaffRule,
    StaffRuleKind,
)
from procworks.store import (
    InstanceStore,
    OrgStore,
    SchemaStore,
    dehydrate_org,
    make_resolver,
)

#: Stable ids so the demo is recognisable and reset-idempotent.
ORG_ID = "org-acme"
SCHEMA_URLAUB = "urlaubsantrag"
SCHEMA_BESCHAFFUNG = "beschaffung"

#: Shared password for every seeded demo login (documented in the README).
#: The demo users skip the forced first-change so they work out of the box.
DEMO_PASSWORD = "demo-procworks"

#: The demo logins seeded in password mode: (login, name, roles, agent id).
DEMO_USERS: list[tuple[str, str, frozenset[str], str | None]] = [
    ("mara.modell", "Mara Modell", frozenset({"modeler"}), None),
    ("erika.sander", "Erika Sander", frozenset({"operator"}), "a-erika"),
    ("tom.berger", "Tom Berger", frozenset({"operator"}), "a-tom"),
    ("vera.viewer", "Vera Viewer", frozenset({"viewer"}), None),
]


def _nid(schema: ProcessSchema, label: str) -> str:
    """Return the id of the (unique) node carrying ``label``."""

    return next(n.id for n in schema.nodes.values() if n.label == label)


def _gateway_id(schema: ProcessSchema, node_type: NodeType) -> str:
    """Return the id of the (unique) gateway node of ``node_type``."""

    return next(n.id for n in schema.nodes.values() if n.type is node_type)


def _label(schema: ProcessSchema, node_id: str) -> str | None:
    node = schema.nodes.get(node_id)
    return node.label if node is not None else None


def _role(role_id: str) -> StaffRule:
    return StaffRule(kind=StaffRuleKind.ROLE, ref=role_id)


def _build_org() -> OrgModel:
    """The shared organisation reused by both example processes."""

    org = org_ops.create_org_model("ACME Mittelstand GmbH", org_id=ORG_ID)
    org = org_ops.org_add_role(org, "Sachbearbeiter", role_id="sachbearbeiter")
    org = org_ops.org_add_role(org, "Teamleitung", role_id="teamleitung")
    org = org_ops.org_add_role(org, "Einkauf", role_id="einkauf")
    org = org_ops.org_add_unit(org, "Vertrieb", org_unit_id="vertrieb")
    org = org_ops.org_add_unit(org, "Einkauf", org_unit_id="einkauf-abt")
    org = org_ops.org_add_agent(
        org, "Erika Sander", role_ids=["sachbearbeiter"], org_unit_id="vertrieb", agent_id="a-erika"
    )
    org = org_ops.org_add_agent(
        org, "Tom Berger", role_ids=["teamleitung"], org_unit_id="vertrieb", agent_id="a-tom"
    )
    org = org_ops.org_add_agent(
        org,
        "Nina Wolf",
        role_ids=["sachbearbeiter"],
        org_unit_id="vertrieb",
        agent_id="a-nina",
        deputy_id="a-erika",
    )
    org = org_ops.org_add_agent(
        org, "Paul Klein", role_ids=["einkauf"], org_unit_id="einkauf-abt", agent_id="a-paul"
    )
    org = org_ops.org_set_manager(org, "vertrieb", "a-tom")
    return org


def _build_urlaubsantrag(org: OrgModel) -> ProcessSchema:
    """Released process: a leave request with an approval/rejection decision."""

    s = ops.create_empty_schema("Urlaubsantrag", schema_id=SCHEMA_URLAUB)
    s = ops.serial_insert(s, "Antrag erfassen", after_node_id="start")
    erfassen = _nid(s, "Antrag erfassen")
    s = ops.serial_insert(s, "Antrag pr\u00fcfen", after_node_id=erfassen)
    pruefen = _nid(s, "Antrag pr\u00fcfen")
    s = ops.conditional_insert(
        s,
        [("tage <= 10", "Genehmigung durch Leitung"), ("tage > 10", "Ablehnung dokumentieren")],
        after_node_id=pruefen,
    )
    join = _gateway_id(s, NodeType.XOR_JOIN)
    s = ops.serial_insert(s, "Mitarbeiter benachrichtigen", after_node_id=join)

    s = ops.add_data_element(s, "Urlaubstage", DataType.INTEGER, element_id="tage")
    s = ops.connect_data(s, erfassen, "tage", AccessMode.WRITE)
    s = ops.connect_data(s, pruefen, "tage", AccessMode.READ)

    s = ops.link_org_model(s, ORG_ID, org)
    s = ops.assign_staff_rule(s, erfassen, _role("sachbearbeiter"))
    s = ops.assign_staff_rule(s, pruefen, _role("sachbearbeiter"))
    s = ops.assign_staff_rule(s, _nid(s, "Genehmigung durch Leitung"), _role("teamleitung"))
    s = ops.assign_staff_rule(s, _nid(s, "Ablehnung dokumentieren"), _role("sachbearbeiter"))
    s = ops.assign_staff_rule(s, _nid(s, "Mitarbeiter benachrichtigen"), _role("sachbearbeiter"))
    return ops.release(s)


def _build_beschaffung(org: OrgModel) -> ProcessSchema:
    """Draft process: a procurement request with a parallel block (still ENTWURF)."""

    s = ops.create_empty_schema("Beschaffungsantrag", schema_id=SCHEMA_BESCHAFFUNG)
    s = ops.parallel_insert(s, ["Angebote einholen", "Budget pr\u00fcfen"], after_node_id="start")
    join = _gateway_id(s, NodeType.AND_JOIN)
    s = ops.serial_insert(s, "Bestellung freigeben", after_node_id=join)

    s = ops.add_data_element(s, "Bestellwert", DataType.FLOAT, element_id="betrag")

    s = ops.link_org_model(s, ORG_ID, org)
    s = ops.assign_staff_rule(s, _nid(s, "Angebote einholen"), _role("einkauf"))
    s = ops.assign_staff_rule(s, _nid(s, "Budget pr\u00fcfen"), _role("teamleitung"))
    s = ops.assign_staff_rule(s, _nid(s, "Bestellung freigeben"), _role("teamleitung"))
    return s  # left in ENTWURF on purpose: shows a draft / test-instance state


def _emit(
    audit: AuditLog,
    event_type: EventType,
    instance: ProcessInstance,
    *,
    node_id: str | None = None,
    label: str | None = None,
    agent_id: str | None = None,
    detail: dict[str, str] | None = None,
) -> None:
    audit.append(
        event_type,
        instance.id,
        instance.schema_id,
        schema_version=instance.schema_version,
        node_id=node_id,
        label=label,
        agent_id=agent_id,
        detail=detail,
    )


def _start(
    schema: ProcessSchema, ctx: exe.ExecutionContext, audit: AuditLog, instance_id: str
) -> ProcessInstance:
    inst = exe.instantiate(schema, instance_id=instance_id, context=ctx)
    _emit(audit, EventType.INSTANCE_CREATED, inst)
    return inst


def _complete(
    schema: ProcessSchema,
    inst: ProcessInstance,
    node_id: str,
    ctx: exe.ExecutionContext,
    audit: AuditLog,
    *,
    agent_id: str | None = None,
    data: dict[str, object] | None = None,
) -> ProcessInstance:
    after = exe.complete_activity(inst, schema, node_id, data, agent_id=agent_id, context=ctx)
    _emit(
        audit,
        EventType.ACTIVITY_COMPLETED,
        after,
        node_id=node_id,
        label=_label(schema, node_id),
        agent_id=agent_id,
    )
    if after.state is InstanceState.COMPLETED:
        _emit(audit, EventType.INSTANCE_COMPLETED, after)
    ctx.instances.put(after)
    return after


def _decide(
    schema: ProcessSchema,
    inst: ProcessInstance,
    split_id: str,
    target_node_id: str,
    ctx: exe.ExecutionContext,
    audit: AuditLog,
) -> ProcessInstance:
    after = exe.decide_branch(inst, schema, split_id, target_node_id, context=ctx)
    _emit(
        audit,
        EventType.BRANCH_DECIDED,
        after,
        node_id=split_id,
        label=_label(schema, split_id),
        detail={"target_node_id": target_node_id},
    )
    ctx.instances.put(after)
    return after


def _seed_instances(
    schema: ProcessSchema, instance_store: InstanceStore, audit: AuditLog
) -> None:
    """Create three leave-request instances at different points in the flow."""

    ctx = exe.ExecutionContext(make_resolver(_NoopSchemaStore()), instance_store)
    erfassen = _nid(schema, "Antrag erfassen")
    pruefen = _nid(schema, "Antrag pr\u00fcfen")
    split = _gateway_id(schema, NodeType.XOR_SPLIT)
    genehmigung = _nid(schema, "Genehmigung durch Leitung")
    ablehnung = _nid(schema, "Ablehnung dokumentieren")
    benachrichtigen = _nid(schema, "Mitarbeiter benachrichtigen")

    # 1) Freshly started -- waiting at the very first activity.
    _start(schema, ctx, audit, "urlaub-2026-001")

    # 2) In progress -- captured and checked, now awaiting management approval.
    i2 = _start(schema, ctx, audit, "urlaub-2026-002")
    i2 = _complete(schema, i2, erfassen, ctx, audit, agent_id="a-erika", data={"tage": 8})
    i2 = _complete(schema, i2, pruefen, ctx, audit, agent_id="a-erika")
    _decide(schema, i2, split, genehmigung, ctx, audit)

    # 3) Finished -- a rejected request that ran all the way to the end.
    i3 = _start(schema, ctx, audit, "urlaub-2026-003")
    i3 = _complete(schema, i3, erfassen, ctx, audit, agent_id="a-erika", data={"tage": 20})
    i3 = _complete(schema, i3, pruefen, ctx, audit, agent_id="a-erika")
    i3 = _decide(schema, i3, split, ablehnung, ctx, audit)
    i3 = _complete(schema, i3, ablehnung, ctx, audit, agent_id="a-erika")
    _complete(schema, i3, benachrichtigen, ctx, audit, agent_id="a-erika")


class _NoopSchemaStore:
    """A throwaway empty schema store for the instance execution context.

    The demo drives execution against the in-memory released schema directly;
    the resolver is only consulted for sub-processes, of which the demo has
    none, so an empty store is sufficient (and keeps the loader self-contained).
    """

    def put(self, schema: ProcessSchema) -> ProcessSchema:
        return schema

    def get(self, schema_id: str) -> ProcessSchema | None:
        return None

    def list_ids(self) -> list[str]:
        return []

    def clear(self) -> None:
        return None


def _seed_users(backend: PasswordAuthBackend) -> int:
    """Seed the ready-to-use demo logins (idempotent); returns how many added."""

    store = backend.store
    seeded = 0
    for login, name, roles, agent_id in DEMO_USERS:
        if store.get_user(login) is not None:
            continue
        store.put_user(
            User(
                login=login,
                password_hash=hash_password(DEMO_PASSWORD),
                subject=login,
                agent_id=agent_id,
                roles=roles,
                display_name=name,
                must_change=False,
            )
        )
        seeded += 1
    return seeded


def load_demo(
    *,
    schema_store: SchemaStore,
    instance_store: InstanceStore,
    org_store: OrgStore,
    audit_log: AuditLog,
    password_backend: PasswordAuthBackend | None = None,
) -> int:
    """Populate the stores with the demo world; returns the seeded-user count.

    Call this on an already-empty system (the admin reset clears first). The
    shared org, both schemas and the three instances are always created; demo
    logins are only seeded when password login is active (otherwise the open
    dev mode already grants every role and needs no users).
    """

    org = _build_org()
    org_store.put(org)

    urlaub = _build_urlaubsantrag(org)
    beschaffung = _build_beschaffung(org)
    schema_store.put(dehydrate_org(urlaub))
    schema_store.put(dehydrate_org(beschaffung))

    _seed_instances(urlaub, instance_store, audit_log)

    if password_backend is not None:
        return _seed_users(password_backend)
    return 0
