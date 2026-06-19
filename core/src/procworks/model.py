# SPDX-License-Identifier: BUSL-1.1
"""Meta-model (Pydantic) for the block-structured process schema.

This mirrors Section 4 of the architecture concept: Node, ControlEdge and the
versioned ProcessSchema with a lifecycle state, the data-flow layer
(DataElement, DataAccess) used by the data-flow rules D1-D4, and the resource
layer (OrgModel, StaffRule, ServiceBinding) used by the resource rules Z1-Z4.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    """Node types of the block-structured control graph."""

    START = "START"
    END = "END"
    ACTIVITY = "ACTIVITY"
    AND_SPLIT = "AND_SPLIT"
    AND_JOIN = "AND_JOIN"
    XOR_SPLIT = "XOR_SPLIT"
    XOR_JOIN = "XOR_JOIN"
    SUBPROCESS = "SUBPROCESS"


#: Gateway node types that open a block.
SPLIT_TYPES = frozenset({NodeType.AND_SPLIT, NodeType.XOR_SPLIT})
#: Gateway node types that close a block.
JOIN_TYPES = frozenset({NodeType.AND_JOIN, NodeType.XOR_JOIN})
#: Matching split -> join pairs (K1).
SPLIT_JOIN_PAIR = {
    NodeType.AND_SPLIT: NodeType.AND_JOIN,
    NodeType.XOR_SPLIT: NodeType.XOR_JOIN,
}


class EdgeType(StrEnum):
    """Control edge types (SYNC/LOOP reserved for later roadmap steps)."""

    CONTROL = "CONTROL"


class LifecycleState(StrEnum):
    """Schema lifecycle states (Section 4.1)."""

    ENTWURF = "ENTWURF"
    REVIEW = "REVIEW"
    RELEASED = "RELEASED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class DataType(StrEnum):
    """Data element value types (Section 3.2)."""

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    URI = "URI"


class AccessMode(StrEnum):
    """Direction of a data access between an activity and a data element."""

    READ = "READ"
    WRITE = "WRITE"
    READ_WRITE = "READ_WRITE"


class DataSourceKind(StrEnum):
    """Where a data element is stored (Section 9.1).

    ``INSTANCE`` values live in the process instance; ``EXTERNAL`` values are
    resolved through a connector against a central database/application.
    """

    INSTANCE = "INSTANCE"
    EXTERNAL = "EXTERNAL"


class ConnectorKind(StrEnum):
    """The external system a connector talks to (Section 9.2).

    ``CUSTOM`` is the open connector SPI for further systems (REST/files/...).
    """

    MS_SQL = "MS_SQL"
    MYSQL = "MYSQL"
    DYNAMICS_365 = "DYNAMICS_365"
    SAP = "SAP"
    CUSTOM = "CUSTOM"


class ExternalBinding(BaseModel):
    """Binds an EXTERNAL data element to a connector entity (Section 9.1).

    ``connector_id`` selects a registered connector, ``entity`` names the
    business object (table/entity/BAPI), and ``key_element_id`` references the
    INSTANCE data element whose value is the lookup key. The key is passed as a
    parameter at access time -- never concatenated into a query (no injection).
    """

    connector_id: str
    entity: str
    key_element_id: str



#: Access modes that read a data element.
READ_MODES = frozenset({AccessMode.READ, AccessMode.READ_WRITE})
#: Access modes that write a data element.
WRITE_MODES = frozenset({AccessMode.WRITE, AccessMode.READ_WRITE})


class NodeState(StrEnum):
    """Runtime node marking (NS) of a process instance (Section 4 / step 8)."""

    NOT_ACTIVATED = "NOT_ACTIVATED"
    ACTIVATED = "ACTIVATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class EdgeState(StrEnum):
    """Runtime edge marking (ES) of a process instance."""

    NOT_SIGNALED = "NOT_SIGNALED"
    TRUE_SIGNALED = "TRUE_SIGNALED"
    FALSE_SIGNALED = "FALSE_SIGNALED"


class InstanceState(StrEnum):
    """Lifecycle state of a running process instance."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


class Node(BaseModel):
    """A node of the control graph."""

    id: str
    type: NodeType
    label: str = ""


class DataElement(BaseModel):
    """A process instance variable (Section 3.2).

    ``source`` selects the storage scope (Section 9.1): ``INSTANCE`` values
    live in the process instance, ``EXTERNAL`` values are resolved through a
    connector via ``external`` (the connector rules C1-C3 keep that binding
    consistent).
    """

    id: str
    name: str
    data_type: DataType
    source: DataSourceKind = DataSourceKind.INSTANCE
    external: ExternalBinding | None = None


class DataAccess(BaseModel):
    """A typed read/write link between an ACTIVITY and a data element.

    ``mandatory`` marks a non-optional parameter: a mandatory read must be
    supplied on every path (D1); a mandatory write guarantees a supply.
    ``param_type`` is the activity parameter type; if set it must match the
    element type (D3).
    """

    node_id: str
    element_id: str
    mode: AccessMode
    mandatory: bool = True
    param_type: DataType | None = None


class ConnectorDescriptor(BaseModel):
    """A registered data connector (Section 9.2).

    The descriptor only carries modelling metadata; credentials and endpoints
    live server-side in a secret store, never in the schema.
    """

    id: str
    name: str
    kind: ConnectorKind


# --- resource / organisation model (Z1-Z4) -------------------------------


class Role(BaseModel):
    """An organisational role (e.g. ``Sachbearbeiter``)."""

    id: str
    name: str


class OrgUnit(BaseModel):
    """An organisational unit; ``parent_id`` builds the unit hierarchy.

    ``manager_id`` names the supervisor (an agent) responsible for the unit.
    """

    id: str
    name: str
    parent_id: str | None = None
    manager_id: str | None = None


class Agent(BaseModel):
    """A concrete actor that can perform interactive steps.

    ``deputy_id`` names another agent that stands in for this one: whenever
    this agent is eligible for a task, the deputy is eligible too (the
    substitution chain is followed transitively at runtime).
    """

    id: str
    name: str
    role_ids: list[str] = Field(default_factory=list)
    org_unit_id: str | None = None
    deputy_id: str | None = None


class OrgModel(BaseModel):
    """The organisational model a staff rule is resolved against.

    An org model can be **embedded** in a single schema (the default; ``id`` is
    ``None``) or a **shared**, standalone master-data entity reused across many
    schemas (``id``/``name`` set, stored in its own registry). A schema that
    references a shared org model via ``ProcessSchema.org_model_id`` resolves
    staff rules against that shared model, so one organisation can be modelled
    once and used in several process models.
    """

    id: str | None = None
    name: str = ""
    roles: dict[str, Role] = Field(default_factory=dict)
    org_units: dict[str, OrgUnit] = Field(default_factory=dict)
    agents: dict[str, Agent] = Field(default_factory=dict)


class StaffRuleKind(StrEnum):
    """Node kinds of the structured staff-assignment rule (BZR) tree."""

    ROLE = "ROLE"
    ORG_UNIT = "ORG_UNIT"
    NODE_PERFORMING_AGENT = "NODE_PERFORMING_AGENT"
    AND = "AND"
    OR = "OR"
    EXCEPT = "EXCEPT"


#: Leaf staff-rule kinds (reference an org element or a prior node).
STAFF_LEAF_KINDS = frozenset(
    {StaffRuleKind.ROLE, StaffRuleKind.ORG_UNIT, StaffRuleKind.NODE_PERFORMING_AGENT}
)
#: Combinator staff-rule kinds (operate on operands).
STAFF_COMBINATOR_KINDS = frozenset(
    {StaffRuleKind.AND, StaffRuleKind.OR, StaffRuleKind.EXCEPT}
)


class StaffRule(BaseModel):
    """A structured staff-assignment rule (BZR) as an expression tree.

    Leaf kinds carry ``ref`` (a role/org-unit/node id); ``recursive`` applies
    to ``ORG_UNIT`` to include sub-units (the ADEPT ``*``/``+`` modifiers).
    Combinator kinds (AND/OR/EXCEPT) carry ``operands``.
    """

    kind: StaffRuleKind
    ref: str | None = None
    recursive: bool = False
    operands: list[StaffRule] = Field(default_factory=list)


# --- activity repository (templates, A1-A3) -------------------------------


class ExecutorKind(StrEnum):
    """How an activity template is executed (Section 6).

    ``MANUAL`` steps are interactive (need a staff rule); the others run
    automatically (script, internal service call, or remote web service).
    """

    MANUAL = "MANUAL"
    SCRIPT = "SCRIPT"
    SERVICE = "SERVICE"
    WEB_SERVICE = "WEB_SERVICE"


class TemplateParameter(BaseModel):
    """A typed input/output parameter of an activity template."""

    name: str
    data_type: DataType
    mandatory: bool = True


class ActivityTemplate(BaseModel):
    """A reusable activity component with a typed I/O interface (Section 6).

    Templates homogenise services "upwards" (logical procedures with typed
    parameters) and carry the executor that runs them "downwards". Binding a
    template to a node enables Plug-&-Play modelling and a data-flow check
    against the declared interface (A1-A3).
    """

    id: str
    name: str
    executor: ExecutorKind
    inputs: list[TemplateParameter] = Field(default_factory=list)
    outputs: list[TemplateParameter] = Field(default_factory=list)

    @property
    def is_automatic(self) -> bool:
        """Whether the executor runs without an interactive performer."""

        return self.executor is not ExecutorKind.MANUAL


class ServiceBinding(BaseModel):
    """The executing service (ActivityTemplate) bound to an ACTIVITY node.

    ``automatic`` distinguishes automated steps (no staff rule needed) from
    interactive steps (which require a staff rule for release). When
    ``template_id`` references a repository template, ``parameter_mapping``
    maps each template parameter name to a schema data-element id, and the
    binding is checked against the template interface (A1-A3).
    """

    node_id: str
    name: str
    automatic: bool = False
    template_id: str | None = None
    parameter_mapping: dict[str, str] = Field(default_factory=dict)


# --- composition: sub-processes and follow-up links (H1-H4, F1-F3) --------


class FollowUpMode(StrEnum):
    """Coupling mode of a follow-up process (Section 4.2)."""

    ASYNC = "ASYNC"
    SYNC = "SYNC"


class FollowUpTrigger(StrEnum):
    """When a follow-up process is started."""

    ON_COMPLETE = "ON_COMPLETE"
    CONDITIONAL = "CONDITIONAL"


class SubProcessBinding(BaseModel):
    """Binds a SUBPROCESS node to a pinned, RELEASED target schema (H1-H4).

    ``input_mapping`` maps a target input data-element id to a parent
    data-element id (the parent supplies the sub-process input);
    ``output_mapping`` maps a target output data-element id to a parent
    data-element id (the sub-process writes back into the parent).
    """

    node_id: str
    target_schema_id: str
    target_version: int
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)


class FollowUpLink(BaseModel):
    """A lateral link to a follow-up process started after this one (F1-F3).

    ``handover_mapping`` maps a target start data-element id to a source
    data-element id of this schema. ``target_version`` ``None`` means "latest
    RELEASED".
    """

    id: str
    target_schema_id: str
    target_version: int | None = None
    trigger: FollowUpTrigger = FollowUpTrigger.ON_COMPLETE
    condition: str | None = None
    handover_mapping: dict[str, str] = Field(default_factory=dict)
    mode: FollowUpMode = FollowUpMode.ASYNC


class ControlEdge(BaseModel):
    """A directed control edge between two nodes."""

    source: str
    target: str
    type: EdgeType = EdgeType.CONTROL
    #: Branch predicate, only meaningful on edges leaving an XOR_SPLIT.
    condition: str | None = None


class ProcessSchema(BaseModel):
    """A versioned, block-structured process schema."""

    id: str
    name: str
    version: int = 1
    lifecycle_state: LifecycleState = LifecycleState.ENTWURF
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: list[ControlEdge] = Field(default_factory=list)
    data_elements: dict[str, DataElement] = Field(default_factory=dict)
    data_accesses: list[DataAccess] = Field(default_factory=list)
    connectors: dict[str, ConnectorDescriptor] = Field(default_factory=dict)
    org_model: OrgModel = Field(default_factory=OrgModel)
    #: When set, the schema uses a shared, standalone org model (resolved from
    #: the org registry by this id) instead of its embedded ``org_model``. The
    #: embedded field is then a hydrated, in-memory cache only -- the shared
    #: model in the registry is the single source of truth.
    org_model_id: str | None = None
    staff_rules: dict[str, StaffRule] = Field(default_factory=dict)
    service_bindings: dict[str, ServiceBinding] = Field(default_factory=dict)
    activity_templates: dict[str, ActivityTemplate] = Field(default_factory=dict)
    sub_process_bindings: dict[str, SubProcessBinding] = Field(default_factory=dict)
    follow_up_links: list[FollowUpLink] = Field(default_factory=list)

    # --- read helpers -----------------------------------------------------

    def start_node(self) -> Node:
        return next(n for n in self.nodes.values() if n.type is NodeType.START)

    def end_node(self) -> Node:
        return next(n for n in self.nodes.values() if n.type is NodeType.END)

    def outgoing(self, node_id: str) -> list[ControlEdge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming(self, node_id: str) -> list[ControlEdge]:
        return [e for e in self.edges if e.target == node_id]

    def accesses_of(self, node_id: str) -> list[DataAccess]:
        return [a for a in self.data_accesses if a.node_id == node_id]

    def writers_of(self, element_id: str) -> list[DataAccess]:
        return [
            a
            for a in self.data_accesses
            if a.element_id == element_id and a.mode in WRITE_MODES
        ]

    def readers_of(self, element_id: str) -> list[DataAccess]:
        return [
            a
            for a in self.data_accesses
            if a.element_id == element_id and a.mode in READ_MODES
        ]


class ProcessInstance(BaseModel):
    """A running instance of a RELEASED schema (Execution Engine, step 8).

    The instance carries the ADEPT-style markings: a node marking (NS) per node
    and an edge marking (ES) per control edge. ``decisions`` records the chosen
    branch of each XOR_SPLIT; ``data_values`` holds the process variables.
    """

    id: str
    schema_id: str
    schema_version: int = 1
    state: InstanceState = InstanceState.RUNNING
    node_states: dict[str, NodeState] = Field(default_factory=dict)
    edge_states: dict[str, EdgeState] = Field(default_factory=dict)
    decisions: dict[str, str] = Field(default_factory=dict)
    data_values: dict[str, object] = Field(default_factory=dict)
    #: Records which agent performed a (completed) node, keyed by node id.
    #: Drives runtime resolution of NodePerformingAgent staff rules and the
    #: per-agent task list.
    performed_by: dict[str, str] = Field(default_factory=dict)
    #: Composition wiring for sub-process execution (step 9 runtime). A child
    #: instance points back to the spawning parent; the parent records, per
    #: SUBPROCESS node, the id of the child instance it started.
    parent_instance_id: str | None = None
    parent_node_id: str | None = None
    child_instances: dict[str, str] = Field(default_factory=dict)
    #: Ids of the decoupled follow-up instances this instance started on
    #: completion (F3, ASYNC). Kept for traceability only.
    follow_up_instances: list[str] = Field(default_factory=list)
    #: Instance-specific ad-hoc schema variant (step 10). When set the engine
    #: runs this instance against this schema instead of the released base; the
    #: ids of executed nodes/edges stay stable so the markings remain valid.
    ad_hoc_schema: ProcessSchema | None = None
    #: Human-readable log of the applied ad-hoc deltas (R1/R2), used for
    #: traceability and the migration ad-hoc compatibility check (M5).
    ad_hoc_deltas: list[str] = Field(default_factory=list)
