"""High-level change operations (Section 7).

These are the *only* way to mutate a schema. Each operation:
  1. checks its preconditions (``requires``),
  2. produces a candidate schema,
  3. validates it (validate-before-commit) and only then returns it.

Because the operations always construct balanced blocks and every result is
validated, an incorrect schema can never be produced or persisted -- this is
Correctness by Construction in practice.
"""

from __future__ import annotations

import itertools

from procworks.model import (
    AccessMode,
    ActivityTemplate,
    Agent,
    ConnectorDescriptor,
    ConnectorKind,
    ControlEdge,
    DataAccess,
    DataElement,
    DataSourceKind,
    DataType,
    ExecutorKind,
    ExternalBinding,
    FollowUpLink,
    FollowUpMode,
    FollowUpTrigger,
    LifecycleState,
    Node,
    NodeType,
    OrgUnit,
    ProcessSchema,
    Role,
    ServiceBinding,
    StaffRule,
    SubProcessBinding,
    TemplateParameter,
)
from procworks.validator import (
    CorrectnessError,
    SchemaResolver,
    ValidationFinding,
    raise_if_invalid,
)

_counter = itertools.count(1)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{next(_counter)}"


def create_empty_schema(name: str, schema_id: str | None = None) -> ProcessSchema:
    """Create the minimal correct schema: START -> END."""

    start = Node(id="start", type=NodeType.START, label="Start")
    end = Node(id="end", type=NodeType.END, label="Ende")
    schema = ProcessSchema(
        id=schema_id or _new_id("schema"),
        name=name,
        nodes={start.id: start, end.id: end},
        edges=[ControlEdge(source=start.id, target=end.id)],
    )
    return raise_if_invalid(schema)


def _require_editable(schema: ProcessSchema) -> None:
    if schema.lifecycle_state is not LifecycleState.ENTWURF:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="R0",
                    message=(
                        f"schema is {schema.lifecycle_state.value}; only ENTWURF is editable"
                    ),
                )
            ]
        )


def _require_node(schema: ProcessSchema, node_id: str) -> Node:
    node = schema.nodes.get(node_id)
    if node is None:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"node '{node_id}' does not exist")]
        )
    return node


def _single_outgoing(schema: ProcessSchema, node_id: str) -> ControlEdge:
    out = schema.outgoing(node_id)
    if len(out) != 1:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    node_id=node_id,
                    message=(
                        f"insertion anchor must have exactly one outgoing edge (has {len(out)})"
                    ),
                )
            ]
        )
    return out[0]


def serial_insert(schema: ProcessSchema, label: str, after_node_id: str) -> ProcessSchema:
    """Insert a single ACTIVITY sequentially after ``after_node_id``.

    requires: schema editable; anchor exists and is not END; anchor has one
              outgoing edge.
    ensures:  new activity spliced between anchor and its successor; K1-K3 hold.
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    anchor = _require_node(candidate, after_node_id)
    if anchor.type is NodeType.END:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", node_id=after_node_id, message="cannot insert after END")]
        )
    edge = _single_outgoing(candidate, after_node_id)
    successor_id = edge.target

    new_node = Node(id=_new_id("act"), type=NodeType.ACTIVITY, label=label)
    candidate.nodes[new_node.id] = new_node
    candidate.edges.remove(edge)
    candidate.edges.append(ControlEdge(source=after_node_id, target=new_node.id))
    candidate.edges.append(ControlEdge(source=new_node.id, target=successor_id))
    return raise_if_invalid(candidate)


def parallel_insert(
    schema: ProcessSchema, branch_labels: list[str], after_node_id: str
) -> ProcessSchema:
    """Insert a balanced AND block (one activity per branch) after the anchor.

    requires: schema editable; anchor exists and is not END; >= 2 branches.
    ensures:  AND_SPLIT/AND_JOIN with N parallel activity branches; K1-K3 hold.
    """

    if len(branch_labels) < 2:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message="parallel_insert requires at least 2 branches")]
        )
    return _insert_block(schema, after_node_id, NodeType.AND_SPLIT, branch_labels, conditions=None)


def conditional_insert(
    schema: ProcessSchema, branches: list[tuple[str, str]], after_node_id: str
) -> ProcessSchema:
    """Insert a balanced XOR block after the anchor.

    ``branches`` is a list of (condition, label) pairs.

    requires: schema editable; anchor exists and is not END; >= 2 branches.
    ensures:  XOR_SPLIT/XOR_JOIN with N conditional activity branches; K1-K3 hold.
    """

    if len(branches) < 2:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP", message="conditional_insert requires at least 2 branches"
                )
            ]
        )
    labels = [label for _, label in branches]
    conditions = [cond for cond, _ in branches]
    return _insert_block(schema, after_node_id, NodeType.XOR_SPLIT, labels, conditions)


def _insert_block(
    schema: ProcessSchema,
    after_node_id: str,
    split_type: NodeType,
    branch_labels: list[str],
    conditions: list[str] | None,
) -> ProcessSchema:
    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    anchor = _require_node(candidate, after_node_id)
    if anchor.type is NodeType.END:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", node_id=after_node_id, message="cannot insert after END")]
        )
    edge = _single_outgoing(candidate, after_node_id)
    successor_id = edge.target

    join_type = {
        NodeType.AND_SPLIT: NodeType.AND_JOIN,
        NodeType.XOR_SPLIT: NodeType.XOR_JOIN,
    }[split_type]

    split = Node(id=_new_id("split"), type=split_type)
    join = Node(id=_new_id("join"), type=join_type)
    candidate.nodes[split.id] = split
    candidate.nodes[join.id] = join

    candidate.edges.remove(edge)
    candidate.edges.append(ControlEdge(source=after_node_id, target=split.id))
    candidate.edges.append(ControlEdge(source=join.id, target=successor_id))

    for i, label in enumerate(branch_labels):
        branch = Node(id=_new_id("act"), type=NodeType.ACTIVITY, label=label)
        candidate.nodes[branch.id] = branch
        condition = conditions[i] if conditions is not None else None
        candidate.edges.append(
            ControlEdge(source=split.id, target=branch.id, condition=condition)
        )
        candidate.edges.append(ControlEdge(source=branch.id, target=join.id))

    return raise_if_invalid(candidate)


def add_data_element(
    schema: ProcessSchema,
    name: str,
    data_type: DataType,
    element_id: str | None = None,
) -> ProcessSchema:
    """Add a process data element (instance variable).

    requires: schema editable; element id is unique.
    ensures:  a new data element exists; D1-D4 still hold.
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    eid = element_id or _new_id("data")
    if eid in candidate.data_elements:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"data element '{eid}' already exists")]
        )
    candidate.data_elements[eid] = DataElement(id=eid, name=name, data_type=data_type)
    return raise_if_invalid(candidate)


def connect_data(
    schema: ProcessSchema,
    node_id: str,
    element_id: str,
    mode: AccessMode,
    *,
    mandatory: bool = True,
    param_type: DataType | None = None,
) -> ProcessSchema:
    """Connect an ACTIVITY to a data element via a read/write access.

    requires: schema editable; node exists and is an ACTIVITY; element exists.
    ensures:  the access is added and the data-flow rules D1-D4 still hold
              (e.g. a mandatory read whose source is not written on all paths
              is rejected with a D1 finding).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    node = _require_node(candidate, node_id)
    if node.type is not NodeType.ACTIVITY:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    node_id=node_id,
                    message="data access is only allowed on ACTIVITY nodes",
                )
            ]
        )
    if element_id not in candidate.data_elements:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"data element '{element_id}' does not exist")]
        )
    candidate.data_accesses.append(
        DataAccess(
            node_id=node_id,
            element_id=element_id,
            mode=mode,
            mandatory=mandatory,
            param_type=param_type,
        )
    )
    return raise_if_invalid(candidate)


def register_connector(
    schema: ProcessSchema,
    name: str,
    kind: ConnectorKind,
    *,
    connector_id: str | None = None,
) -> ProcessSchema:
    """Register a data connector in the schema's connector registry (Section 9).

    requires: schema editable; connector id is unique.
    ensures:  the connector is available for external data bindings (C1).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    cid = connector_id or _new_id("connector")
    if cid in candidate.connectors:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"connector '{cid}' already exists")]
        )
    candidate.connectors[cid] = ConnectorDescriptor(id=cid, name=name, kind=kind)
    return raise_if_invalid(candidate)


def bind_external_data(
    schema: ProcessSchema,
    element_id: str,
    *,
    connector_id: str,
    entity: str,
    key_element_id: str,
) -> ProcessSchema:
    """Turn a data element into an EXTERNAL element resolved via a connector.

    requires: schema editable; the element exists.
    ensures:  the element's source is EXTERNAL and the connector rules C1-C3
              hold (registered connector, INSTANCE key element, non-empty
              entity).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    element = candidate.data_elements.get(element_id)
    if element is None:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"data element '{element_id}' does not exist")]
        )
    element.source = DataSourceKind.EXTERNAL
    element.external = ExternalBinding(
        connector_id=connector_id,
        entity=entity,
        key_element_id=key_element_id,
    )
    return raise_if_invalid(candidate)


def add_role(schema: ProcessSchema, name: str, role_id: str | None = None) -> ProcessSchema:
    """Add an organisational role to the schema's org model."""

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    rid = role_id or _new_id("role")
    if rid in candidate.org_model.roles:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"role '{rid}' already exists")]
        )
    candidate.org_model.roles[rid] = Role(id=rid, name=name)
    return raise_if_invalid(candidate)


def add_org_unit(
    schema: ProcessSchema,
    name: str,
    parent_id: str | None = None,
    org_unit_id: str | None = None,
    manager_id: str | None = None,
) -> ProcessSchema:
    """Add an organisational unit (optionally below an existing parent unit).

    ``manager_id`` (optional) names the supervisor agent; it must reference an
    existing agent (checked via Z1).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    uid = org_unit_id or _new_id("unit")
    if uid in candidate.org_model.org_units:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"org unit '{uid}' already exists")]
        )
    if parent_id is not None and parent_id not in candidate.org_model.org_units:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"parent org unit '{parent_id}' does not exist")]
        )
    candidate.org_model.org_units[uid] = OrgUnit(
        id=uid, name=name, parent_id=parent_id, manager_id=manager_id
    )
    return raise_if_invalid(candidate)


def add_agent(
    schema: ProcessSchema,
    name: str,
    role_ids: list[str] | None = None,
    org_unit_id: str | None = None,
    agent_id: str | None = None,
    deputy_id: str | None = None,
) -> ProcessSchema:
    """Add an agent (actor) and link it to existing roles / an org unit.

    ``deputy_id`` (optional) names a stand-in agent; it must reference an
    existing agent and cannot be the agent itself (checked via Z1).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    aid = agent_id or _new_id("agent")
    if aid in candidate.org_model.agents:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"agent '{aid}' already exists")]
        )
    roles = role_ids or []
    for role_id in roles:
        if role_id not in candidate.org_model.roles:
            raise CorrectnessError(
                [ValidationFinding(rule="OP", message=f"role '{role_id}' does not exist")]
            )
    if org_unit_id is not None and org_unit_id not in candidate.org_model.org_units:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"org unit '{org_unit_id}' does not exist")]
        )
    candidate.org_model.agents[aid] = Agent(
        id=aid, name=name, role_ids=roles, org_unit_id=org_unit_id, deputy_id=deputy_id
    )
    return raise_if_invalid(candidate)


def set_org_unit_manager(
    schema: ProcessSchema, org_unit_id: str, manager_id: str | None
) -> ProcessSchema:
    """Set (or clear with ``None``) the supervisor of an org unit.

    Manager and deputy assignments are org master data, not process structure;
    they may therefore be changed on a RELEASED schema too, taking immediate
    effect for running instances. The result is still validated (Z1).
    """

    candidate = schema.model_copy(deep=True)
    unit = candidate.org_model.org_units.get(org_unit_id)
    if unit is None:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"org unit '{org_unit_id}' does not exist")]
        )
    unit.manager_id = manager_id
    return raise_if_invalid(candidate)


def set_org_unit_parent(
    schema: ProcessSchema, org_unit_id: str, parent_id: str | None
) -> ProcessSchema:
    """Move an org unit below another parent (or to the top with ``None``).

    The organisational hierarchy is master data that mirrors reality, so a
    re-org may be applied to a RELEASED schema too (it takes immediate effect
    for running instances via recursive ORG_UNIT resolution). The result is
    validated (Z1). A move that would create a cycle -- making the unit its own
    ancestor -- is rejected, since the tree must stay acyclic.
    """

    candidate = schema.model_copy(deep=True)
    units = candidate.org_model.org_units
    unit = units.get(org_unit_id)
    if unit is None:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"org unit '{org_unit_id}' does not exist")]
        )
    if parent_id is not None:
        if parent_id not in units:
            raise CorrectnessError(
                [
                    ValidationFinding(
                        rule="OP",
                        message=f"parent org unit '{parent_id}' does not exist",
                    )
                ]
            )
        if parent_id == org_unit_id:
            raise CorrectnessError(
                [ValidationFinding(rule="OP", message="an org unit cannot be its own parent")]
            )
        # Walk up from the prospective parent; hitting the unit means a cycle.
        cursor: str | None = parent_id
        seen: set[str] = set()
        while cursor is not None and cursor not in seen:
            if cursor == org_unit_id:
                raise CorrectnessError(
                    [
                        ValidationFinding(
                            rule="OP",
                            message="move would create a cycle in the org hierarchy",
                        )
                    ]
                )
            seen.add(cursor)
            cursor = units[cursor].parent_id
    unit.parent_id = parent_id
    return raise_if_invalid(candidate)


def set_agent_deputy(
    schema: ProcessSchema, agent_id: str, deputy_id: str | None
) -> ProcessSchema:
    """Set (or clear with ``None``) an agent's deputy (Vertreter).

    A person defines their own stand-in; this is org master data and may be
    changed on a RELEASED schema too. The result is validated (Z1: the deputy
    must exist and differ from the agent).
    """

    candidate = schema.model_copy(deep=True)
    agent = candidate.org_model.agents.get(agent_id)
    if agent is None:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"agent '{agent_id}' does not exist")]
        )
    agent.deputy_id = deputy_id
    return raise_if_invalid(candidate)


def add_activity_template(
    schema: ProcessSchema,
    name: str,
    executor: ExecutorKind,
    *,
    inputs: list[TemplateParameter] | None = None,
    outputs: list[TemplateParameter] | None = None,
    template_id: str | None = None,
) -> ProcessSchema:
    """Add a reusable activity template to the repository (Section 6).

    requires: schema editable; ``template_id`` (if given) is not already used.
    ensures:  the template is stored and the schema stays correct.
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    tid = template_id or _new_id("template")
    if tid in candidate.activity_templates:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    message=f"activity template '{tid}' already exists",
                )
            ]
        )
    candidate.activity_templates[tid] = ActivityTemplate(
        id=tid,
        name=name,
        executor=executor,
        inputs=list(inputs or []),
        outputs=list(outputs or []),
    )
    return raise_if_invalid(candidate)


def assign_service(
    schema: ProcessSchema,
    node_id: str,
    name: str,
    *,
    automatic: bool = False,
    template_id: str | None = None,
    parameter_mapping: dict[str, str] | None = None,
) -> ProcessSchema:
    """Bind an executing service (ActivityTemplate) to an ACTIVITY node.

    requires: schema editable; node exists and is an ACTIVITY; if
              ``template_id`` is given it must exist in the repository.
    ensures:  the service binding is set and the resource/repository rules
              Z1-Z4 and A1-A3 hold. When a template is referenced, ``automatic``
              is derived from its executor so the binding is consistent (A2).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    node = _require_node(candidate, node_id)
    if node.type is not NodeType.ACTIVITY:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    node_id=node_id,
                    message="service can only be bound to ACTIVITY nodes",
                )
            ]
        )
    if template_id is not None:
        template = candidate.activity_templates.get(template_id)
        if template is None:
            raise CorrectnessError(
                [
                    ValidationFinding(
                        rule="OP",
                        node_id=node_id,
                        message=f"unknown activity template '{template_id}'",
                    )
                ]
            )
        automatic = template.is_automatic
    candidate.service_bindings[node_id] = ServiceBinding(
        node_id=node_id,
        name=name,
        automatic=automatic,
        template_id=template_id,
        parameter_mapping=dict(parameter_mapping or {}),
    )
    return raise_if_invalid(candidate)


def assign_staff_rule(
    schema: ProcessSchema, node_id: str, rule: StaffRule
) -> ProcessSchema:
    """Assign a staff-assignment rule (BZR) to an ACTIVITY node.

    requires: schema editable; node exists and is an ACTIVITY.
    ensures:  the rule is stored and the resource rules Z1-Z4 hold (e.g. an
              unknown role yields Z1, an unsatisfiable rule yields Z2, an
              invalid NodePerformingAgent back-reference yields Z3).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    node = _require_node(candidate, node_id)
    if node.type is not NodeType.ACTIVITY:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    node_id=node_id,
                    message="staff rule can only be assigned to ACTIVITY nodes",
                )
            ]
        )
    candidate.staff_rules[node_id] = rule
    return raise_if_invalid(candidate)


def release(schema: ProcessSchema, resolver: SchemaResolver | None = None) -> ProcessSchema:
    """Release the schema (lifecycle transition ENTWURF/REVIEW -> RELEASED).

    requires: structural correctness (Stufe A: K1-K3 hold).
    ensures:  schema becomes RELEASED (immutable for further edits).

    ``resolver`` enables the cross-schema composition checks (H1: a SUBPROCESS
    must reference a RELEASED target). Note: full Stufe-B checks (B1-B3:
    services, staff rules, data bindings) are added in later roadmap steps.
    """

    if schema.lifecycle_state not in (LifecycleState.ENTWURF, LifecycleState.REVIEW):
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="LC",
                    message=f"cannot release from state {schema.lifecycle_state.value}",
                )
            ]
        )
    raise_if_invalid(schema, resolver)
    released = schema.model_copy(deep=True)
    released.lifecycle_state = LifecycleState.RELEASED
    return released


def new_revision(schema: ProcessSchema, *, new_schema_id: str | None = None) -> ProcessSchema:
    """Derive an editable next revision (version + 1) of a RELEASED schema.

    The copy keeps all node/edge/data element ids so a later instance migration
    (M2/M3) can match the already-executed region by id. It starts in ENTWURF
    and gets a fresh schema id (the single-version store keys by id, so the new
    revision is stored alongside its predecessor).

    requires: schema is RELEASED.
    ensures:  returns an ENTWURF copy with ``version`` incremented.
    """

    if schema.lifecycle_state is not LifecycleState.RELEASED:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="LC",
                    message=(
                        f"can only revise a RELEASED schema, not {schema.lifecycle_state.value}"
                    ),
                )
            ]
        )
    revision = schema.model_copy(deep=True)
    revision.id = new_schema_id or _new_id("schema")
    revision.version = schema.version + 1
    revision.lifecycle_state = LifecycleState.ENTWURF
    return raise_if_invalid(revision)


def insert_subprocess(
    schema: ProcessSchema,
    after_node_id: str,
    target_schema_id: str,
    target_version: int,
    *,
    label: str = "",
    input_mapping: dict[str, str] | None = None,
    output_mapping: dict[str, str] | None = None,
    resolver: SchemaResolver | None = None,
) -> ProcessSchema:
    """Insert a SUBPROCESS node sequentially and bind it to a target schema.

    requires: schema editable; anchor exists, is not END, has one outgoing
              edge.
    ensures:  new SUBPROCESS spliced in with a binding; K1-K3 and H1-H4 hold
              (the latter only fully when a ``resolver`` is provided).
    """

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    anchor = _require_node(candidate, after_node_id)
    if anchor.type is NodeType.END:
        raise CorrectnessError(
            [ValidationFinding(rule="OP", node_id=after_node_id, message="cannot insert after END")]
        )
    edge = _single_outgoing(candidate, after_node_id)
    successor_id = edge.target

    new_node = Node(id=_new_id("sub"), type=NodeType.SUBPROCESS, label=label)
    candidate.nodes[new_node.id] = new_node
    candidate.edges.remove(edge)
    candidate.edges.append(ControlEdge(source=after_node_id, target=new_node.id))
    candidate.edges.append(ControlEdge(source=new_node.id, target=successor_id))
    candidate.sub_process_bindings[new_node.id] = SubProcessBinding(
        node_id=new_node.id,
        target_schema_id=target_schema_id,
        target_version=target_version,
        input_mapping=input_mapping or {},
        output_mapping=output_mapping or {},
    )
    return raise_if_invalid(candidate, resolver)


def set_subprocess_mapping(
    schema: ProcessSchema,
    node_id: str,
    input_mapping: dict[str, str],
    output_mapping: dict[str, str],
    *,
    resolver: SchemaResolver | None = None,
) -> ProcessSchema:
    """Replace the input/output mapping of an existing sub-process binding."""

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    binding = candidate.sub_process_bindings.get(node_id)
    if binding is None:
        raise CorrectnessError(
            [
                ValidationFinding(
                    rule="OP",
                    node_id=node_id,
                    message=f"node '{node_id}' has no sub-process binding",
                )
            ]
        )
    binding.input_mapping = dict(input_mapping)
    binding.output_mapping = dict(output_mapping)
    return raise_if_invalid(candidate, resolver)


def link_follow_up(
    schema: ProcessSchema,
    target_schema_id: str,
    *,
    target_version: int | None = None,
    trigger: FollowUpTrigger = FollowUpTrigger.ON_COMPLETE,
    condition: str | None = None,
    handover_mapping: dict[str, str] | None = None,
    mode: FollowUpMode = FollowUpMode.ASYNC,
    resolver: SchemaResolver | None = None,
    link_id: str | None = None,
) -> ProcessSchema:
    """Add a follow-up link to another process type (F1-F3)."""

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    candidate.follow_up_links.append(
        FollowUpLink(
            id=link_id or _new_id("followup"),
            target_schema_id=target_schema_id,
            target_version=target_version,
            trigger=trigger,
            condition=condition,
            handover_mapping=handover_mapping or {},
            mode=mode,
        )
    )
    return raise_if_invalid(candidate, resolver)


def unlink_follow_up(schema: ProcessSchema, link_id: str) -> ProcessSchema:
    """Remove a follow-up link by id."""

    candidate = schema.model_copy(deep=True)
    _require_editable(candidate)
    remaining = [link for link in candidate.follow_up_links if link.id != link_id]
    if len(remaining) == len(candidate.follow_up_links):
        raise CorrectnessError(
            [ValidationFinding(rule="OP", message=f"follow-up link '{link_id}' does not exist")]
        )
    candidate.follow_up_links = remaining
    return raise_if_invalid(candidate)
