# SPDX-License-Identifier: BUSL-1.1
"""Correctness Validator (Stufe A, structural rules K1-K3).

The validator is called *before* committing any change operation (validate-
before-commit). It returns precise, localized findings. Operations refuse to
commit a schema that produces any finding, so a persisted schema always
satisfies the structural correctness invariant.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from pydantic import BaseModel

from procworks.conditions import ConditionError, referenced_names
from procworks.model import (
    JOIN_TYPES,
    READ_MODES,
    SPLIT_JOIN_PAIR,
    SPLIT_TYPES,
    STAFF_COMBINATOR_KINDS,
    STAFF_LEAF_KINDS,
    WRITE_MODES,
    ActivityTemplate,
    DataSourceKind,
    FollowUpTrigger,
    LifecycleState,
    NodeType,
    OrgModel,
    ProcessSchema,
    ServiceBinding,
    StaffRule,
    StaffRuleKind,
    SubProcessBinding,
)

#: Resolves a (schema id, version) reference to a schema, or ``None`` if the
#: version is ``None`` it resolves the latest known schema for that id. Used by
#: the cross-schema composition rules (H1-H4, F1-F3).
SchemaResolver = Callable[[str, "int | None"], "ProcessSchema | None"]


class ValidationFinding(BaseModel):
    """A single, localized correctness violation."""

    rule: str
    message: str
    node_id: str | None = None


class CorrectnessError(Exception):
    """Raised when an operation would produce an incorrect schema."""

    def __init__(self, findings: list[ValidationFinding]) -> None:
        self.findings = findings
        super().__init__("; ".join(f"[{f.rule}] {f.message}" for f in findings))


def validate(
    schema: ProcessSchema, resolver: SchemaResolver | None = None
) -> list[ValidationFinding]:
    """Run structural rules K1-K3, data-flow D1-D4, resource rules Z1-Z4,
    activity-repository rules A1-A3 and composition rules H1-H4/F1-F4.

    ``resolver`` enables the cross-schema composition checks (target must be
    RELEASED, type-conformant mappings, acyclic hierarchy). Without it only the
    local well-formedness of sub-process/follow-up references is checked.

    Returns all findings (an empty list means the schema is correct).
    """

    findings: list[ValidationFinding] = []
    findings += _check_k2_endpoints_and_degrees(schema)
    findings += _check_k1_gateways(schema)
    findings += _check_k3_reachability(schema)
    findings += _check_data_flow(schema)
    findings += _check_connectors(schema)
    findings += _check_resources(schema)
    findings += _check_composition(schema, resolver)
    return findings


def raise_if_invalid(
    schema: ProcessSchema, resolver: SchemaResolver | None = None
) -> ProcessSchema:
    """Return the schema if correct, otherwise raise CorrectnessError."""

    findings = validate(schema, resolver)
    if findings:
        raise CorrectnessError(findings)
    return schema


# --- K2: single start/end, well-formed in/out degrees --------------------


def _check_k2_endpoints_and_degrees(schema: ProcessSchema) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    starts = [n for n in schema.nodes.values() if n.type is NodeType.START]
    ends = [n for n in schema.nodes.values() if n.type is NodeType.END]
    if len(starts) != 1:
        findings.append(
            ValidationFinding(rule="K2", message=f"expected exactly one START, found {len(starts)}")
        )
    if len(ends) != 1:
        findings.append(
            ValidationFinding(rule="K2", message=f"expected exactly one END, found {len(ends)}")
        )

    for node in schema.nodes.values():
        ind = len(schema.incoming(node.id))
        outd = len(schema.outgoing(node.id))
        if node.type is NodeType.START:
            if ind != 0 or outd != 1:
                findings.append(_deg(node.id, "START must have in=0, out=1", ind, outd))
        elif node.type is NodeType.END:
            if ind != 1 or outd != 0:
                findings.append(_deg(node.id, "END must have in=1, out=0", ind, outd))
        elif node.type is NodeType.ACTIVITY:
            if ind != 1 or outd != 1:
                findings.append(_deg(node.id, "ACTIVITY must have in=1, out=1", ind, outd))
        elif node.type is NodeType.SUBPROCESS:
            if ind != 1 or outd != 1:
                findings.append(_deg(node.id, "SUBPROCESS must have in=1, out=1", ind, outd))
        elif node.type in SPLIT_TYPES:
            if ind != 1 or outd < 2:
                msg = f"{node.type.value} must have in=1, out>=2"
                findings.append(_deg(node.id, msg, ind, outd))
        elif node.type in JOIN_TYPES:
            if ind < 2 or outd != 1:
                msg = f"{node.type.value} must have in>=2, out=1"
                findings.append(_deg(node.id, msg, ind, outd))

    return findings


def _deg(node_id: str, msg: str, ind: int, outd: int) -> ValidationFinding:
    return ValidationFinding(rule="K2", node_id=node_id, message=f"{msg} (in={ind}, out={outd})")


# --- K1: balanced, matching gateways -------------------------------------


def _check_k1_gateways(schema: ProcessSchema) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for split_type, join_type in SPLIT_JOIN_PAIR.items():
        n_splits = sum(1 for n in schema.nodes.values() if n.type is split_type)
        n_joins = sum(1 for n in schema.nodes.values() if n.type is join_type)
        if n_splits != n_joins:
            findings.append(
                ValidationFinding(
                    rule="K1",
                    message=(
                        f"unbalanced gateways: {n_splits} x {split_type.value} "
                        f"vs {n_joins} x {join_type.value}"
                    ),
                )
            )
    return findings


# --- K3: reachability (no isolated nodes, no dead ends) -------------------


def _check_k3_reachability(schema: ProcessSchema) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not schema.nodes:
        return findings

    starts = [n for n in schema.nodes.values() if n.type is NodeType.START]
    ends = [n for n in schema.nodes.values() if n.type is NodeType.END]
    if len(starts) != 1 or len(ends) != 1:
        # Endpoint cardinality already reported by K2; skip to avoid noise.
        return findings

    forward = _bfs({s.id for s in starts}, _succ_map(schema))
    backward = _bfs({e.id for e in ends}, _pred_map(schema))

    for node in schema.nodes.values():
        if node.id not in forward:
            findings.append(
                ValidationFinding(
                    rule="K3", node_id=node.id, message="node not reachable from START"
                )
            )
        if node.id not in backward:
            findings.append(
                ValidationFinding(
                    rule="K3", node_id=node.id, message="node cannot reach END (dead end)"
                )
            )
    return findings


def _succ_map(schema: ProcessSchema) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {nid: [] for nid in schema.nodes}
    for e in schema.edges:
        out.setdefault(e.source, []).append(e.target)
    return out


def _pred_map(schema: ProcessSchema) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {nid: [] for nid in schema.nodes}
    for e in schema.edges:
        out.setdefault(e.target, []).append(e.source)
    return out


def _bfs(starts: set[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set(starts)
    queue: deque[str] = deque(starts)
    while queue:
        current = queue.popleft()
        for nxt in adjacency.get(current, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


# --- D1-D4: data-flow correctness ----------------------------------------


def _check_data_flow(schema: ProcessSchema) -> list[ValidationFinding]:
    """Run data-flow rules D4 (well-formedness), D3 (types), D2 and D1."""

    findings: list[ValidationFinding] = []
    findings += _check_d4_wellformed(schema)
    findings += _check_d3_types(schema)
    # D1/D2 rely on a well-formed control graph; skip if the structure or the
    # data accesses are already broken to avoid noisy follow-up errors.
    if findings or _structure_broken(schema):
        return findings
    findings += _check_d2_concurrent_writes(schema)
    findings += _check_d1_supply(schema)
    return findings


def _structure_broken(schema: ProcessSchema) -> bool:
    """True if structural rules already fail (then D1/D2 are not meaningful)."""

    return bool(
        _check_k2_endpoints_and_degrees(schema)
        or _check_k1_gateways(schema)
        or _check_k3_reachability(schema)
    )


def _check_d4_wellformed(schema: ProcessSchema) -> list[ValidationFinding]:
    """D4: data accesses only on ACTIVITY nodes and to existing elements."""

    findings: list[ValidationFinding] = []
    for access in schema.data_accesses:
        node = schema.nodes.get(access.node_id)
        if node is None:
            findings.append(
                ValidationFinding(
                    rule="D4",
                    node_id=access.node_id,
                    message=f"data access references unknown node '{access.node_id}'",
                )
            )
        elif node.type is not NodeType.ACTIVITY:
            findings.append(
                ValidationFinding(
                    rule="D4",
                    node_id=access.node_id,
                    message=f"only ACTIVITY nodes may access data, not {node.type.value}",
                )
            )
        if access.element_id not in schema.data_elements:
            findings.append(
                ValidationFinding(
                    rule="D4",
                    node_id=access.node_id,
                    message=f"data access references unknown element '{access.element_id}'",
                )
            )
    return findings


def _check_d3_types(schema: ProcessSchema) -> list[ValidationFinding]:
    """D3: declared parameter type must match the data element type."""

    findings: list[ValidationFinding] = []
    for access in schema.data_accesses:
        element = schema.data_elements.get(access.element_id)
        if element is None or access.param_type is None:
            continue
        if access.param_type != element.data_type:
            findings.append(
                ValidationFinding(
                    rule="D3",
                    node_id=access.node_id,
                    message=(
                        f"parameter type {access.param_type.value} does not match "
                        f"element '{element.name}' type {element.data_type.value}"
                    ),
                )
            )
    return findings


def _check_d1_supply(schema: ProcessSchema) -> list[ValidationFinding]:
    """D1: every mandatory read is supplied by a mandatory write on all paths."""

    findings: list[ValidationFinding] = []
    written_before = _must_written_before(schema)
    for access in schema.data_accesses:
        if access.mode not in READ_MODES or not access.mandatory:
            continue
        element = schema.data_elements.get(access.element_id)
        if element is None:
            continue
        if access.element_id not in written_before.get(access.node_id, set()):
            findings.append(
                ValidationFinding(
                    rule="D1",
                    node_id=access.node_id,
                    message=(
                        f"mandatory input '{element.name}' may be read before it is "
                        f"written on some execution path"
                    ),
                )
            )
    return findings


def _must_written_before(schema: ProcessSchema) -> dict[str, set[str]]:
    """For each node, the elements guaranteed written on all paths before it.

    Forward must-analysis over the (acyclic) control graph: at an AND_JOIN all
    branches run, so contributions are unioned; at an XOR_JOIN only one branch
    runs, so contributions are intersected.
    """

    order = _topological_order(schema)
    pred = _pred_map(schema)
    mandatory_writes: dict[str, set[str]] = {nid: set() for nid in schema.nodes}
    for access in schema.data_accesses:
        if access.mode in WRITE_MODES and access.mandatory:
            mandatory_writes.setdefault(access.node_id, set()).add(access.element_id)

    before: dict[str, set[str]] = {nid: set() for nid in schema.nodes}
    available_after: dict[str, set[str]] = {}
    for node_id in order:
        predecessors = pred.get(node_id, [])
        if not predecessors:
            guaranteed: set[str] = set()
        else:
            contributions = [available_after.get(p, set()) for p in predecessors]
            if schema.nodes[node_id].type is NodeType.AND_JOIN:
                guaranteed = set().union(*contributions)
            else:
                guaranteed = set(contributions[0]).intersection(*contributions[1:])
        before[node_id] = guaranteed
        available_after[node_id] = guaranteed | mandatory_writes.get(node_id, set())
    return before


def _check_d2_concurrent_writes(schema: ProcessSchema) -> list[ValidationFinding]:
    """D2: no two mandatory writes to the same element on parallel AND branches."""

    findings: list[ValidationFinding] = []
    succ = _succ_map(schema)
    reachable = {nid: _bfs(set(succ.get(nid, [])), succ) for nid in schema.nodes}

    writers: dict[str, list[str]] = {}
    for access in schema.data_accesses:
        if access.mode in WRITE_MODES and access.mandatory:
            writers.setdefault(access.element_id, []).append(access.node_id)

    for element_id, nodes in writers.items():
        unique = sorted(set(nodes))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                a, b = unique[i], unique[j]
                if b in reachable[a] or a in reachable[b]:
                    continue  # sequentially ordered -> not concurrent
                if _parallel_under_and(schema, a, b, reachable):
                    element = schema.data_elements.get(element_id)
                    name = element.name if element else element_id
                    findings.append(
                        ValidationFinding(
                            rule="D2",
                            node_id=a,
                            message=(
                                f"concurrent writes to data element '{name}' on "
                                f"parallel AND branches ({a}, {b})"
                            ),
                        )
                    )
    return findings


def _parallel_under_and(
    schema: ProcessSchema, a: str, b: str, reachable: dict[str, set[str]]
) -> bool:
    """True if a and b sit on different branches of a common AND_SPLIT."""

    common_splits = [
        nid
        for nid, node in schema.nodes.items()
        if node.type in SPLIT_TYPES and a in reachable[nid] and b in reachable[nid]
    ]
    if not common_splits:
        return False
    # Innermost common split: the one reachable from all other common splits.
    for candidate in common_splits:
        if all(other == candidate or candidate in reachable[other] for other in common_splits):
            return schema.nodes[candidate].type is NodeType.AND_SPLIT
    return False


def _topological_order(schema: ProcessSchema) -> list[str]:
    succ = _succ_map(schema)
    indegree = {nid: 0 for nid in schema.nodes}
    for edge in schema.edges:
        indegree[edge.target] = indegree.get(edge.target, 0) + 1
    queue: deque[str] = deque(nid for nid, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for nxt in succ.get(node_id, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return order


def _must_executed_before(schema: ProcessSchema) -> dict[str, set[str]]:
    """For each node, the nodes guaranteed to have executed on all prior paths.

    Same must-analysis as the data flow (AND_JOIN unions branches, XOR_JOIN
    intersects them), but tracking node execution instead of data writes. Used
    by Z3 to validate NodePerformingAgent back-references.
    """

    order = _topological_order(schema)
    pred = _pred_map(schema)
    before: dict[str, set[str]] = {nid: set() for nid in schema.nodes}
    executed_after: dict[str, set[str]] = {}
    for node_id in order:
        predecessors = pred.get(node_id, [])
        if not predecessors:
            guaranteed: set[str] = set()
        else:
            contributions = [executed_after.get(p, set()) for p in predecessors]
            if schema.nodes[node_id].type is NodeType.AND_JOIN:
                guaranteed = set().union(*contributions)
            else:
                guaranteed = set(contributions[0]).intersection(*contributions[1:])
        before[node_id] = guaranteed
        executed_after[node_id] = guaranteed | {node_id}
    return before


# --- C1-C3: external data connectors -------------------------------------


def _check_connectors(schema: ProcessSchema) -> list[ValidationFinding]:
    """Connector rules C1-C3 for EXTERNAL data elements (Section 9).

    C1: an EXTERNAL element carries an ``external`` binding to a registered
        connector (and an INSTANCE element carries none).
    C2: the binding's key references an existing INSTANCE data element (the
        process supplies the lookup key; it is not itself external) and is not
        the element itself.
    C3: the bound entity name is non-empty.
    """

    findings: list[ValidationFinding] = []
    for element in schema.data_elements.values():
        if element.source is DataSourceKind.INSTANCE:
            if element.external is not None:
                findings.append(
                    ValidationFinding(
                        rule="C1",
                        message=(
                            f"INSTANCE element '{element.id}' must not carry an "
                            f"external binding"
                        ),
                    )
                )
            continue
        binding = element.external
        if binding is None:
            findings.append(
                ValidationFinding(
                    rule="C1",
                    message=f"EXTERNAL element '{element.id}' is missing its external binding",
                )
            )
            continue
        if binding.connector_id not in schema.connectors:
            findings.append(
                ValidationFinding(
                    rule="C1",
                    message=(
                        f"element '{element.id}' references unknown connector "
                        f"'{binding.connector_id}'"
                    ),
                )
            )
        if not binding.entity.strip():
            findings.append(
                ValidationFinding(
                    rule="C3",
                    message=f"element '{element.id}' has an empty connector entity",
                )
            )
        if binding.key_element_id == element.id:
            findings.append(
                ValidationFinding(
                    rule="C2",
                    message=f"element '{element.id}' uses itself as its lookup key",
                )
            )
            continue
        key_element = schema.data_elements.get(binding.key_element_id)
        if key_element is None:
            findings.append(
                ValidationFinding(
                    rule="C2",
                    message=(
                        f"element '{element.id}' uses unknown key element "
                        f"'{binding.key_element_id}'"
                    ),
                )
            )
        elif key_element.source is not DataSourceKind.INSTANCE:
            findings.append(
                ValidationFinding(
                    rule="C2",
                    message=(
                        f"key element '{binding.key_element_id}' of '{element.id}' must be "
                        f"an INSTANCE element"
                    ),
                )
            )
    return findings


# --- Z1-Z4: resource / staff-assignment correctness ----------------------


def _check_resources(schema: ProcessSchema) -> list[ValidationFinding]:
    """Run resource rules Z1 (well-formed), Z4 (service), the activity
    repository rules A1-A3, and (if well-formed) Z2 and Z3."""

    findings: list[ValidationFinding] = []
    findings += _check_z1_wellformed(schema)
    findings += _check_org_master_data(schema)
    findings += _check_z4_service(schema)
    findings += _check_activity_repository(schema)
    # Z2/Z3 evaluate the rule and the control graph; only run them when the
    # rules are well-formed (Z1) and the structure is intact.
    if findings or _structure_broken(schema):
        return findings
    findings += _check_z2_resolvable(schema)
    findings += _check_z3_backrefs(schema)
    return findings


def _check_org_master_data(schema: ProcessSchema) -> list[ValidationFinding]:
    """Z1: referential integrity of org master data (managers and deputies).

    A unit's ``manager_id`` and an agent's ``deputy_id`` must reference an
    existing agent; an agent cannot be its own deputy. Deputy chains may form
    cycles in principle -- runtime resolution follows them with a visited
    guard, so cycles are tolerated rather than rejected here.
    """

    findings: list[ValidationFinding] = []
    org = schema.org_model
    for unit in org.org_units.values():
        if unit.manager_id is not None and unit.manager_id not in org.agents:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    message=f"org unit '{unit.id}' has unknown manager '{unit.manager_id}'",
                )
            )
    for agent in org.agents.values():
        if agent.deputy_id is None:
            continue
        if agent.deputy_id == agent.id:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    message=f"agent '{agent.id}' cannot be its own deputy",
                )
            )
        elif agent.deputy_id not in org.agents:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    message=f"agent '{agent.id}' has unknown deputy '{agent.deputy_id}'",
                )
            )
    return findings


def _check_z1_wellformed(schema: ProcessSchema) -> list[ValidationFinding]:
    """Z1: staff rules are well-formed and reference existing elements."""

    findings: list[ValidationFinding] = []
    for node_id, rule in schema.staff_rules.items():
        node = schema.nodes.get(node_id)
        if node is None:
            findings.append(
                ValidationFinding(
                    rule="Z1", node_id=node_id, message=f"staff rule on unknown node '{node_id}'"
                )
            )
        elif node.type is not NodeType.ACTIVITY:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    node_id=node_id,
                    message=(
                        f"staff rules are only allowed on ACTIVITY nodes, "
                        f"not {node.type.value}"
                    ),
                )
            )
        findings += _check_staff_rule_node(schema, node_id, rule)
    return findings


def _check_staff_rule_node(
    schema: ProcessSchema, node_id: str, rule: StaffRule
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if rule.kind in STAFF_LEAF_KINDS:
        if rule.operands:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    node_id=node_id,
                    message=f"{rule.kind.value} term must have no operands",
                )
            )
        if rule.ref is None:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    node_id=node_id,
                    message=f"{rule.kind.value} term requires a reference",
                )
            )
        else:
            findings += _check_staff_ref(schema, node_id, rule)
    elif rule.kind in STAFF_COMBINATOR_KINDS:
        min_operands = 2 if rule.kind is StaffRuleKind.EXCEPT else 1
        if rule.kind is StaffRuleKind.EXCEPT and len(rule.operands) != 2:
            findings.append(
                ValidationFinding(
                    rule="Z1", node_id=node_id, message="EXCEPT requires exactly two operands"
                )
            )
        elif len(rule.operands) < min_operands:
            findings.append(
                ValidationFinding(
                    rule="Z1",
                    node_id=node_id,
                    message=f"{rule.kind.value} requires at least {min_operands} operand(s)",
                )
            )
        for operand in rule.operands:
            findings += _check_staff_rule_node(schema, node_id, operand)
    return findings


def _check_staff_ref(
    schema: ProcessSchema, node_id: str, rule: StaffRule
) -> list[ValidationFinding]:
    org = schema.org_model
    ref = rule.ref
    if rule.kind is StaffRuleKind.ROLE and ref not in org.roles:
        return [
            ValidationFinding(rule="Z1", node_id=node_id, message=f"unknown role '{ref}'")
        ]
    if rule.kind is StaffRuleKind.ORG_UNIT and ref not in org.org_units:
        return [
            ValidationFinding(rule="Z1", node_id=node_id, message=f"unknown org unit '{ref}'")
        ]
    if rule.kind is StaffRuleKind.NODE_PERFORMING_AGENT and ref not in schema.nodes:
        return [
            ValidationFinding(
                rule="Z1",
                node_id=node_id,
                message=f"NodePerformingAgent references unknown node '{ref}'",
            )
        ]
    return []


def _check_z4_service(schema: ProcessSchema) -> list[ValidationFinding]:
    """Z4: service bindings are well-formed; automatic steps carry no staff rule."""

    findings: list[ValidationFinding] = []
    for node_id, binding in schema.service_bindings.items():
        node = schema.nodes.get(node_id)
        if node is None or node.type is not NodeType.ACTIVITY:
            findings.append(
                ValidationFinding(
                    rule="Z4",
                    node_id=node_id,
                    message="service binding is only allowed on ACTIVITY nodes",
                )
            )
            continue
        if binding.automatic and node_id in schema.staff_rules:
            findings.append(
                ValidationFinding(
                    rule="Z4",
                    node_id=node_id,
                    message="automatic step must not carry a staff rule (BZR)",
                )
            )
    return findings


def _check_activity_repository(schema: ProcessSchema) -> list[ValidationFinding]:
    """Activity Repository rules A1-A3 for template-bound services.

    A1: a referenced template must exist in the repository.
    A2: the binding's ``automatic`` flag must match the template's executor.
    A3: the template interface must be bound type-conformantly -- every
        mandatory parameter is mapped, mapped names belong to the template, and
        each mapped data element exists with a matching type.
    Free-form bindings (no ``template_id``) are left untouched.
    """

    findings: list[ValidationFinding] = []
    for node_id, binding in schema.service_bindings.items():
        if binding.template_id is None:
            continue
        template = schema.activity_templates.get(binding.template_id)
        if template is None:
            findings.append(
                ValidationFinding(
                    rule="A1",
                    node_id=node_id,
                    message=f"service binding references unknown template '{binding.template_id}'",
                )
            )
            continue
        if binding.automatic != template.is_automatic:
            findings.append(
                ValidationFinding(
                    rule="A2",
                    node_id=node_id,
                    message=(
                        f"binding 'automatic' ({binding.automatic}) does not match the "
                        f"{template.executor.value} executor of template '{template.id}'"
                    ),
                )
            )
        findings += _check_template_interface(schema, node_id, binding, template)
    return findings


def _check_template_interface(
    schema: ProcessSchema,
    node_id: str,
    binding: ServiceBinding,
    template: ActivityTemplate,
) -> list[ValidationFinding]:
    """A3: the parameter mapping conforms to the template interface."""

    findings: list[ValidationFinding] = []
    parameters = {p.name: p for p in [*template.inputs, *template.outputs]}
    for param in parameters.values():
        if param.mandatory and param.name not in binding.parameter_mapping:
            findings.append(
                ValidationFinding(
                    rule="A3",
                    node_id=node_id,
                    message=f"mandatory parameter '{param.name}' is not bound",
                )
            )
    for param_name, element_id in binding.parameter_mapping.items():
        mapped_param = parameters.get(param_name)
        if mapped_param is None:
            findings.append(
                ValidationFinding(
                    rule="A3",
                    node_id=node_id,
                    message=f"template '{template.id}' has no parameter '{param_name}'",
                )
            )
            continue
        element = schema.data_elements.get(element_id)
        if element is None:
            findings.append(
                ValidationFinding(
                    rule="A3",
                    node_id=node_id,
                    message=f"parameter '{param_name}' is bound to unknown element '{element_id}'",
                )
            )
        elif element.data_type is not mapped_param.data_type:
            findings.append(
                ValidationFinding(
                    rule="A3",
                    node_id=node_id,
                    message=(
                        f"parameter '{param_name}' ({mapped_param.data_type.value}) does not match "
                        f"element '{element_id}' ({element.data_type.value})"
                    ),
                )
            )
    return findings


def _check_z2_resolvable(schema: ProcessSchema) -> list[ValidationFinding]:
    """Z2: each staff rule can potentially resolve to at least one agent."""

    findings: list[ValidationFinding] = []
    for node_id, rule in schema.staff_rules.items():
        possible = _possible_agents(schema.org_model, rule)
        if possible is not None and not possible:
            findings.append(
                ValidationFinding(
                    rule="Z2",
                    node_id=node_id,
                    message="staff rule cannot resolve to any agent in the org model",
                )
            )
    return findings


def _possible_agents(org: OrgModel, rule: StaffRule) -> set[str] | None:
    """Over-approximation of the agents a rule could resolve to (for Z2).

    Returns ``None`` for the unbounded 'universe' (a NodePerformingAgent is
    bound to some agent at runtime, so it is always potentially non-empty,
    even against an empty org model). A concrete empty set means the rule is
    definitely unsatisfiable. EXCEPT only removes, so its upper bound is the
    left operand's possible set.
    """

    if rule.kind is StaffRuleKind.ROLE:
        return {a.id for a in org.agents.values() if rule.ref in a.role_ids}
    if rule.kind is StaffRuleKind.ORG_UNIT:
        units = {rule.ref} | _descendant_units(org, rule.ref, rule.recursive)
        return {a.id for a in org.agents.values() if a.org_unit_id in units}
    if rule.kind is StaffRuleKind.NODE_PERFORMING_AGENT:
        return None  # universe: resolved at runtime
    operand_sets = [_possible_agents(org, op) for op in rule.operands]
    if rule.kind is StaffRuleKind.AND:
        return _intersect_bounds(operand_sets)
    if rule.kind is StaffRuleKind.OR:
        return _union_bounds(operand_sets)
    # EXCEPT: upper bound is the left operand (removing agents cannot add any).
    return operand_sets[0]


def _intersect_bounds(bounds: list[set[str] | None]) -> set[str] | None:
    result: set[str] | None = None  # None == universe
    for bound in bounds:
        if bound is None:
            continue
        result = bound if result is None else (result & bound)
    return result


def _union_bounds(bounds: list[set[str] | None]) -> set[str] | None:
    result: set[str] = set()
    for bound in bounds:
        if bound is None:
            return None  # union with universe is universe
        result |= bound
    return result


def _descendant_units(org: OrgModel, unit_id: str | None, recursive: bool) -> set[str]:
    if not recursive or unit_id is None:
        return set()
    descendants: set[str] = set()
    frontier = [unit_id]
    while frontier:
        current = frontier.pop()
        for uid, unit in org.org_units.items():
            if unit.parent_id == current and uid not in descendants:
                descendants.add(uid)
                frontier.append(uid)
    return descendants


def _check_z3_backrefs(schema: ProcessSchema) -> list[ValidationFinding]:
    """Z3: NodePerformingAgent refs must be guaranteed-executed before the node."""

    findings: list[ValidationFinding] = []
    before = _must_executed_before(schema)
    for node_id, rule in schema.staff_rules.items():
        for ref in _node_refs(rule):
            if ref not in before.get(node_id, set()):
                findings.append(
                    ValidationFinding(
                        rule="Z3",
                        node_id=node_id,
                        message=(
                            f"NodePerformingAgent('{ref}') is not guaranteed to run "
                            f"before this node on all paths"
                        ),
                    )
                )
    return findings


def _node_refs(rule: StaffRule) -> set[str]:
    if rule.kind is StaffRuleKind.NODE_PERFORMING_AGENT and rule.ref is not None:
        return {rule.ref}
    refs: set[str] = set()
    for operand in rule.operands:
        refs |= _node_refs(operand)
    return refs


# --- H1-H4 / F1-F3: composition (sub- and follow-up processes) -----------


def _check_composition(
    schema: ProcessSchema, resolver: SchemaResolver | None
) -> list[ValidationFinding]:
    """Run the cross-schema composition rules H1-H4 (sub-processes) and
    F1-F3 (follow-up processes)."""

    findings: list[ValidationFinding] = []
    findings += _check_subprocesses(schema, resolver)
    findings += _check_follow_ups(schema, resolver)
    return findings


def _check_subprocesses(
    schema: ProcessSchema, resolver: SchemaResolver | None
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    # Every SUBPROCESS node must carry a binding, and every binding must point
    # at an existing SUBPROCESS node.
    for node in schema.nodes.values():
        if node.type is NodeType.SUBPROCESS and node.id not in schema.sub_process_bindings:
            findings.append(
                ValidationFinding(
                    rule="H1",
                    node_id=node.id,
                    message="SUBPROCESS node has no sub-process binding",
                )
            )
    for node_id, binding in schema.sub_process_bindings.items():
        bound_node = schema.nodes.get(node_id)
        if bound_node is None or bound_node.type is not NodeType.SUBPROCESS:
            findings.append(
                ValidationFinding(
                    rule="H1",
                    node_id=node_id,
                    message="sub-process binding does not reference a SUBPROCESS node",
                )
            )
            continue
        # H2 (local part): mapped parent elements must exist.
        for parent_eid in (*binding.input_mapping.values(), *binding.output_mapping.values()):
            if parent_eid not in schema.data_elements:
                findings.append(
                    ValidationFinding(
                        rule="H2",
                        node_id=node_id,
                        message=f"mapping references unknown parent data element '{parent_eid}'",
                    )
                )
        if resolver is None:
            continue
        findings += _check_subprocess_target(schema, node_id, binding, resolver)

    if resolver is not None and _has_subprocess_cycle(schema, resolver):
        findings.append(
            ValidationFinding(
                rule="H3",
                message="sub-process hierarchy is cyclic (a process cannot contain itself)",
            )
        )
    return findings


def _check_subprocess_target(
    schema: ProcessSchema,
    node_id: str,
    binding: SubProcessBinding,
    resolver: SchemaResolver,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    target = resolver(binding.target_schema_id, binding.target_version)
    if target is None:
        findings.append(
            ValidationFinding(
                rule="H1",
                node_id=node_id,
                message=(
                    f"sub-process target '{binding.target_schema_id}' "
                    f"v{binding.target_version} not found"
                ),
            )
        )
        return findings
    if target.lifecycle_state is not LifecycleState.RELEASED:
        findings.append(
            ValidationFinding(
                rule="H1",
                node_id=node_id,
                message=(
                    f"sub-process target '{binding.target_schema_id}' is "
                    f"{target.lifecycle_state.value}, must be RELEASED"
                ),
            )
        )
    # H2 (type conformance): each mapped target element must exist and match.
    mappings = (
        ("input", binding.input_mapping),
        ("output", binding.output_mapping),
    )
    for kind, mapping in mappings:
        for target_eid, parent_eid in mapping.items():
            target_el = target.data_elements.get(target_eid)
            parent_el = schema.data_elements.get(parent_eid)
            if target_el is None:
                findings.append(
                    ValidationFinding(
                        rule="H2",
                        node_id=node_id,
                        message=f"{kind} maps unknown target element '{target_eid}'",
                    )
                )
                continue
            if parent_el is not None and target_el.data_type is not parent_el.data_type:
                findings.append(
                    ValidationFinding(
                        rule="H2",
                        node_id=node_id,
                        message=(
                            f"{kind} type mismatch: target '{target_eid}' is "
                            f"{target_el.data_type.value}, parent '{parent_eid}' is "
                            f"{parent_el.data_type.value}"
                        ),
                    )
                )
    return findings


def _has_subprocess_cycle(schema: ProcessSchema, resolver: SchemaResolver) -> bool:
    """True if the transitive sub-process call graph leads back to ``schema``."""

    visited: set[str] = set()

    def visit(target_id: str, version: int | None) -> bool:
        if target_id == schema.id:
            return True
        key = f"{target_id}:{version}"
        if key in visited:
            return False
        visited.add(key)
        target = resolver(target_id, version)
        if target is None:
            return False
        for binding in target.sub_process_bindings.values():
            if visit(binding.target_schema_id, binding.target_version):
                return True
        return False

    return any(
        visit(b.target_schema_id, b.target_version)
        for b in schema.sub_process_bindings.values()
    )


def _check_follow_up_condition(
    schema: ProcessSchema, link_id: str, condition: str | None
) -> list[ValidationFinding]:
    """F4: a CONDITIONAL follow-up's predicate is parseable and only reads
    existing data elements."""

    if condition is None or not condition.strip():
        return [
            ValidationFinding(
                rule="F4",
                message=f"conditional follow-up '{link_id}' has no condition",
            )
        ]
    try:
        names = referenced_names(condition)
    except ConditionError as exc:
        return [
            ValidationFinding(
                rule="F4",
                message=f"follow-up '{link_id}' has an invalid condition: {exc}",
            )
        ]
    findings: list[ValidationFinding] = []
    for name in sorted(names):
        if name not in schema.data_elements:
            findings.append(
                ValidationFinding(
                    rule="F4",
                    message=(
                        f"follow-up '{link_id}' condition references unknown data "
                        f"element '{name}'"
                    ),
                )
            )
    return findings


def _check_follow_ups(
    schema: ProcessSchema, resolver: SchemaResolver | None
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for link in schema.follow_up_links:
        # F2 (local part): mapped source elements must exist.
        for source_eid in link.handover_mapping.values():
            if source_eid not in schema.data_elements:
                findings.append(
                    ValidationFinding(
                        rule="F2",
                        message=(
                            f"follow-up '{link.id}' handover references unknown source "
                            f"element '{source_eid}'"
                        ),
                    )
                )
        # F4: a CONDITIONAL trigger needs a well-formed condition that only
        # reads existing data elements (so it can be evaluated deterministically
        # against an instance's data values at runtime).
        if link.trigger is FollowUpTrigger.CONDITIONAL:
            findings += _check_follow_up_condition(schema, link.id, link.condition)
        if resolver is None:
            continue
        target = resolver(link.target_schema_id, link.target_version)
        if target is None:
            findings.append(
                ValidationFinding(
                    rule="F1",
                    message=(
                        f"follow-up target '{link.target_schema_id}' has no "
                        f"matching released version"
                    ),
                )
            )
            continue
        if target.lifecycle_state is not LifecycleState.RELEASED:
            findings.append(
                ValidationFinding(
                    rule="F1",
                    message=(
                        f"follow-up target '{link.target_schema_id}' is "
                        f"{target.lifecycle_state.value}, must be RELEASED"
                    ),
                )
            )
        # F2 (type conformance): each mapped target start element must match.
        for target_eid, source_eid in link.handover_mapping.items():
            target_el = target.data_elements.get(target_eid)
            source_el = schema.data_elements.get(source_eid)
            if target_el is None:
                findings.append(
                    ValidationFinding(
                        rule="F2",
                        message=(
                            f"follow-up '{link.id}' handover maps unknown target "
                            f"element '{target_eid}'"
                        ),
                    )
                )
                continue
            if source_el is not None and target_el.data_type is not source_el.data_type:
                findings.append(
                    ValidationFinding(
                        rule="F2",
                        message=(
                            f"follow-up '{link.id}' type mismatch: target "
                            f"'{target_eid}' is {target_el.data_type.value}, source "
                            f"'{source_eid}' is {source_el.data_type.value}"
                        ),
                    )
                )
    return findings
