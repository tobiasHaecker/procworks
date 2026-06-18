"""Headless HTTP API (FastAPI) for the procworks kernel.

This is the single entry point to the domain core (Section 5.4, API-first):
the same operations are available to any client -- GUI, CLI, other systems --
and every mutation goes through the validate-before-commit path. The GUI has
no privileged side door.

Run locally:
    uvicorn procworks.api:app --reload
Interactive docs at /docs (OpenAPI is generated automatically).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from procworks import adhoc, assignment, migration
from procworks import bpmn as bpmn_io
from procworks import execution as exe
from procworks import operations as ops
from procworks.assignment import OpenTask
from procworks.audit import (
    AuditEvent,
    EventType,
    KpiReport,
    ProcessMap,
    compute_kpis,
    create_audit_log,
    discover_process_map,
    instance_timeline,
)
from procworks.bpmn import BpmnError
from procworks.execution import ExecutionError
from procworks.model import (
    AccessMode,
    ConnectorKind,
    DataType,
    ExecutorKind,
    FollowUpMode,
    FollowUpTrigger,
    InstanceState,
    ProcessInstance,
    ProcessSchema,
    StaffRule,
    TemplateParameter,
)
from procworks.store import create_instance_store, create_store, make_resolver
from procworks.validator import CorrectnessError, ValidationFinding, validate

app = FastAPI(
    title="Process-Core API",
    version="0.1.0",
    summary="Headless, block-structured process engine kernel (Correctness by Construction).",
)

# The browser-based UI (Section 8) is a thin API client that may be served from
# a different origin (file:// or a static dev server). It holds no correctness
# logic, so a permissive CORS policy is safe for this local kernel: every
# request still passes the same validate-before-commit path.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = create_store()
_instances = create_instance_store()
_resolver = make_resolver(_store)
_context = exe.ExecutionContext(_resolver, _instances)
_audit = create_audit_log()


def _label_of(schema: ProcessSchema, node_id: str) -> str | None:
    """Return the human-readable label of a node, if it exists."""

    node = schema.nodes.get(node_id)
    return node.label if node is not None else None


def _record_completion(before: ProcessInstance, after: ProcessInstance) -> None:
    """Append an INSTANCE_COMPLETED event when an instance has just finished."""

    if (
        before.state is InstanceState.RUNNING
        and after.state is InstanceState.COMPLETED
    ):
        _audit.append(
            EventType.INSTANCE_COMPLETED,
            after.id,
            after.schema_id,
            schema_version=after.schema_version,
        )


# --- request models ------------------------------------------------------


class CreateSchemaRequest(BaseModel):
    name: str = Field(..., examples=["Urlaubsantrag"])


class SerialInsertRequest(BaseModel):
    label: str = Field(..., examples=["Antrag prüfen"])
    after_node_id: str = Field(..., examples=["start"])


class ParallelInsertRequest(BaseModel):
    branch_labels: list[str] = Field(..., examples=[["Fachprüfung", "Budgetprüfung"]])
    after_node_id: str = Field(..., examples=["start"])


class Branch(BaseModel):
    condition: str = Field(..., examples=["betrag > 1000"])
    label: str = Field(..., examples=["Freigabe Leitung"])


class ConditionalInsertRequest(BaseModel):
    branches: list[Branch]
    after_node_id: str = Field(..., examples=["start"])


class AddDataElementRequest(BaseModel):
    name: str = Field(..., examples=["betrag"])
    data_type: DataType = Field(..., examples=[DataType.FLOAT])
    element_id: str | None = Field(default=None, examples=["betrag"])


class ConnectDataRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    element_id: str = Field(..., examples=["betrag"])
    mode: AccessMode = Field(..., examples=[AccessMode.READ])
    mandatory: bool = True
    param_type: DataType | None = None


class RegisterConnectorRequest(BaseModel):
    name: str = Field(..., examples=["ERP-Kunden"])
    kind: ConnectorKind = Field(..., examples=[ConnectorKind.MS_SQL])
    connector_id: str | None = Field(default=None, examples=["erp"])


class BindExternalDataRequest(BaseModel):
    connector_id: str = Field(..., examples=["erp"])
    entity: str = Field(..., examples=["Kunde"])
    key_element_id: str = Field(..., examples=["kunden_nr"])


class ImportBpmnRequest(BaseModel):
    xml: str = Field(..., description="BPMN 2.0 XML document")
    name: str | None = Field(default=None, examples=["Importierter Prozess"])
    schema_id: str | None = Field(default=None, examples=["imported"])


class AddRoleRequest(BaseModel):
    name: str = Field(..., examples=["Sachbearbeiter"])
    role_id: str | None = Field(default=None, examples=["sb"])


class AddOrgUnitRequest(BaseModel):
    name: str = Field(..., examples=["Einkauf"])
    parent_id: str | None = None
    org_unit_id: str | None = Field(default=None, examples=["einkauf"])
    manager_id: str | None = Field(default=None, examples=["a1"])


class AddAgentRequest(BaseModel):
    name: str = Field(..., examples=["Erika Muster"])
    role_ids: list[str] = Field(default_factory=list, examples=[["sb"]])
    org_unit_id: str | None = None
    agent_id: str | None = None
    deputy_id: str | None = Field(default=None, examples=["a2"])


class SetManagerRequest(BaseModel):
    manager_id: str | None = Field(default=None, examples=["a1"])


class SetParentRequest(BaseModel):
    parent_id: str | None = Field(default=None, examples=["unit_1"])


class SetDeputyRequest(BaseModel):
    deputy_id: str | None = Field(default=None, examples=["a2"])


class AssignServiceRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    name: str = Field(..., examples=["Antrag erfassen"])
    automatic: bool = False
    template_id: str | None = Field(default=None, examples=["tmpl_erfassen"])
    parameter_mapping: dict[str, str] = Field(default_factory=dict)


class AddActivityTemplateRequest(BaseModel):
    name: str = Field(..., examples=["Antrag erfassen"])
    executor: ExecutorKind = Field(..., examples=[ExecutorKind.MANUAL])
    inputs: list[TemplateParameter] = Field(default_factory=list)
    outputs: list[TemplateParameter] = Field(default_factory=list)
    template_id: str | None = Field(default=None, examples=["tmpl_erfassen"])


class AssignStaffRuleRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    rule: StaffRule


class InsertSubprocessRequest(BaseModel):
    after_node_id: str = Field(..., examples=["start"])
    target_schema_id: str = Field(..., examples=["schema_2"])
    target_version: int = Field(..., examples=[1])
    label: str = ""
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)


class SubprocessMappingRequest(BaseModel):
    node_id: str = Field(..., examples=["sub_1"])
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)


class LinkFollowUpRequest(BaseModel):
    target_schema_id: str = Field(..., examples=["schema_3"])
    target_version: int | None = None
    trigger: FollowUpTrigger = FollowUpTrigger.ON_COMPLETE
    condition: str | None = None
    handover_mapping: dict[str, str] = Field(default_factory=dict)
    mode: FollowUpMode = FollowUpMode.ASYNC


class StartActivityRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])


class CompleteActivityRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    data: dict[str, object] = Field(default_factory=dict)
    agent_id: str | None = Field(default=None, examples=["a1"])


class DecideBranchRequest(BaseModel):
    node_id: str = Field(..., examples=["xor_split_1"])
    target_node_id: str = Field(..., examples=["act_2"])


class AdhocInsertRequest(BaseModel):
    after_node_id: str = Field(..., examples=["act_1"])
    label: str = Field(..., examples=["Zusatzpruefung"])


class AdhocDeleteRequest(BaseModel):
    node_id: str = Field(..., examples=["act_2"])


class RevisionRequest(BaseModel):
    new_schema_id: str | None = Field(default=None, examples=["schema_v2"])


class MigrateRequest(BaseModel):
    target_schema_id: str = Field(..., examples=["schema_v2"])
    data_mapping: dict[str, object] = Field(default_factory=dict)


class MigrationReport(BaseModel):
    migratable: bool
    findings: list[ValidationFinding]


class WorklistReport(BaseModel):
    state: str
    ready_activities: list[str]
    pending_decisions: list[str]


class ValidationReport(BaseModel):
    correct: bool
    findings: list[ValidationFinding]


# --- helpers -------------------------------------------------------------


def _get_or_404(schema_id: str) -> ProcessSchema:
    schema = _store.get(schema_id)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"schema '{schema_id}' not found")
    return schema


def _commit_or_422(result_fn: object) -> ProcessSchema:
    """Execute an operation callable; map CorrectnessError to HTTP 422."""

    try:
        schema = result_fn()  # type: ignore[operator]
    except CorrectnessError as exc:
        raise HTTPException(
            status_code=422,
            detail={"findings": [f.model_dump() for f in exc.findings]},
        ) from exc
    return _store.put(schema)


def _get_instance_or_404(instance_id: str) -> ProcessInstance:
    instance = _instances.get(instance_id)
    if instance is None:
        raise HTTPException(
            status_code=404, detail=f"instance '{instance_id}' not found"
        )
    return instance


def _run_or_409(result_fn: object) -> ProcessInstance:
    """Execute a runtime operation callable; map ExecutionError to HTTP 409."""

    try:
        instance = result_fn()  # type: ignore[operator]
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail={"message": exc.message}) from exc
    return _instances.put(instance)


def _effective_schema_for(instance: ProcessInstance) -> ProcessSchema:
    """Return the schema an instance currently runs against.

    Ad-hoc changed instances carry their own per-instance variant
    (``ad_hoc_schema``); everything else runs against the released base schema.
    """

    base = _get_or_404(instance.schema_id)
    return adhoc.effective_schema(instance, base)


def _commit_instance_or_422(result_fn: object) -> ProcessInstance:
    """Execute an instance change op; map CorrectnessError to HTTP 422."""

    try:
        instance = result_fn()  # type: ignore[operator]
    except CorrectnessError as exc:
        raise HTTPException(
            status_code=422,
            detail={"findings": [f.model_dump() for f in exc.findings]},
        ) from exc
    return _instances.put(instance)



# --- endpoints -----------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/schemas")
def list_schemas() -> list[str]:
    return _store.list_ids()


@app.post("/schemas", response_model=ProcessSchema, status_code=201)
def create_schema(req: CreateSchemaRequest) -> ProcessSchema:
    return _commit_or_422(lambda: ops.create_empty_schema(req.name))


@app.get("/schemas/{schema_id}", response_model=ProcessSchema)
def get_schema(schema_id: str) -> ProcessSchema:
    return _get_or_404(schema_id)


@app.get("/schemas/{schema_id}/validation", response_model=ValidationReport)
def get_validation(schema_id: str) -> ValidationReport:
    schema = _get_or_404(schema_id)
    findings = validate(schema, _resolver)
    return ValidationReport(correct=not findings, findings=findings)


@app.post("/schemas/{schema_id}/serial-insert", response_model=ProcessSchema)
def post_serial_insert(schema_id: str, req: SerialInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.serial_insert(schema, req.label, req.after_node_id))


@app.post("/schemas/{schema_id}/parallel-insert", response_model=ProcessSchema)
def post_parallel_insert(schema_id: str, req: ParallelInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.parallel_insert(schema, req.branch_labels, req.after_node_id)
    )


@app.post("/schemas/{schema_id}/conditional-insert", response_model=ProcessSchema)
def post_conditional_insert(schema_id: str, req: ConditionalInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    branches = [(b.condition, b.label) for b in req.branches]
    return _commit_or_422(lambda: ops.conditional_insert(schema, branches, req.after_node_id))


@app.post("/schemas/{schema_id}/data-elements", response_model=ProcessSchema)
def post_add_data_element(schema_id: str, req: AddDataElementRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_data_element(schema, req.name, req.data_type, req.element_id)
    )


@app.post("/schemas/{schema_id}/data-access", response_model=ProcessSchema)
def post_connect_data(schema_id: str, req: ConnectDataRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.connect_data(
            schema,
            req.node_id,
            req.element_id,
            req.mode,
            mandatory=req.mandatory,
            param_type=req.param_type,
        )
    )


@app.post("/schemas/{schema_id}/connectors", response_model=ProcessSchema)
def post_register_connector(
    schema_id: str, req: RegisterConnectorRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.register_connector(
            schema, req.name, req.kind, connector_id=req.connector_id
        )
    )


@app.post(
    "/schemas/{schema_id}/data-elements/{element_id}/external",
    response_model=ProcessSchema,
)
def post_bind_external_data(
    schema_id: str, element_id: str, req: BindExternalDataRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.bind_external_data(
            schema,
            element_id,
            connector_id=req.connector_id,
            entity=req.entity,
            key_element_id=req.key_element_id,
        )
    )


@app.get("/schemas/{schema_id}/bpmn")
def get_export_bpmn(schema_id: str) -> Response:
    schema = _get_or_404(schema_id)
    return Response(content=bpmn_io.export_bpmn(schema), media_type="application/xml")


@app.post("/bpmn-import", response_model=ProcessSchema, status_code=201)
def post_import_bpmn(req: ImportBpmnRequest) -> ProcessSchema:
    try:
        schema = bpmn_io.import_bpmn(
            req.xml, schema_id=req.schema_id, name=req.name, resolver=_resolver
        )
    except BpmnError as exc:
        raise HTTPException(
            status_code=422, detail={"message": str(exc)}
        ) from exc
    except CorrectnessError as exc:
        raise HTTPException(
            status_code=422,
            detail={"findings": [f.model_dump() for f in exc.findings]},
        ) from exc
    return _store.put(schema)


@app.post("/schemas/{schema_id}/roles", response_model=ProcessSchema)
def post_add_role(schema_id: str, req: AddRoleRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.add_role(schema, req.name, req.role_id))


@app.post("/schemas/{schema_id}/org-units", response_model=ProcessSchema)
def post_add_org_unit(schema_id: str, req: AddOrgUnitRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_org_unit(
            schema, req.name, req.parent_id, req.org_unit_id, req.manager_id
        )
    )


@app.post(
    "/schemas/{schema_id}/org-units/{org_unit_id}/manager",
    response_model=ProcessSchema,
)
def post_set_org_unit_manager(
    schema_id: str, org_unit_id: str, req: SetManagerRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_org_unit_manager(schema, org_unit_id, req.manager_id)
    )


@app.post(
    "/schemas/{schema_id}/org-units/{org_unit_id}/parent",
    response_model=ProcessSchema,
)
def post_set_org_unit_parent(
    schema_id: str, org_unit_id: str, req: SetParentRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_org_unit_parent(schema, org_unit_id, req.parent_id)
    )


@app.post("/schemas/{schema_id}/agents", response_model=ProcessSchema)
def post_add_agent(schema_id: str, req: AddAgentRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_agent(
            schema, req.name, req.role_ids, req.org_unit_id, req.agent_id, req.deputy_id
        )
    )


@app.post(
    "/schemas/{schema_id}/agents/{agent_id}/deputy",
    response_model=ProcessSchema,
)
def post_set_agent_deputy(
    schema_id: str, agent_id: str, req: SetDeputyRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_agent_deputy(schema, agent_id, req.deputy_id)
    )


@app.post("/schemas/{schema_id}/activity-templates", response_model=ProcessSchema)
def post_add_activity_template(
    schema_id: str, req: AddActivityTemplateRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_activity_template(
            schema,
            req.name,
            req.executor,
            inputs=req.inputs,
            outputs=req.outputs,
            template_id=req.template_id,
        )
    )


@app.post("/schemas/{schema_id}/service", response_model=ProcessSchema)
def post_assign_service(schema_id: str, req: AssignServiceRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.assign_service(
            schema,
            req.node_id,
            req.name,
            automatic=req.automatic,
            template_id=req.template_id,
            parameter_mapping=req.parameter_mapping,
        )
    )


@app.post("/schemas/{schema_id}/staff-rule", response_model=ProcessSchema)
def post_assign_staff_rule(schema_id: str, req: AssignStaffRuleRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.assign_staff_rule(schema, req.node_id, req.rule))


@app.post("/schemas/{schema_id}/subprocess", response_model=ProcessSchema)
def post_insert_subprocess(
    schema_id: str, req: InsertSubprocessRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.insert_subprocess(
            schema,
            req.after_node_id,
            req.target_schema_id,
            req.target_version,
            label=req.label,
            input_mapping=req.input_mapping,
            output_mapping=req.output_mapping,
            resolver=_resolver,
        )
    )


@app.post("/schemas/{schema_id}/subprocess-mapping", response_model=ProcessSchema)
def post_subprocess_mapping(
    schema_id: str, req: SubprocessMappingRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_subprocess_mapping(
            schema,
            req.node_id,
            req.input_mapping,
            req.output_mapping,
            resolver=_resolver,
        )
    )


@app.post("/schemas/{schema_id}/follow-up", response_model=ProcessSchema)
def post_link_follow_up(schema_id: str, req: LinkFollowUpRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.link_follow_up(
            schema,
            req.target_schema_id,
            target_version=req.target_version,
            trigger=req.trigger,
            condition=req.condition,
            handover_mapping=req.handover_mapping,
            mode=req.mode,
            resolver=_resolver,
        )
    )


@app.delete("/schemas/{schema_id}/follow-up/{link_id}", response_model=ProcessSchema)
def delete_follow_up(schema_id: str, link_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.unlink_follow_up(schema, link_id))


@app.post("/schemas/{schema_id}/release", response_model=ProcessSchema)
def post_release(schema_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.release(schema, _resolver))


# --- execution endpoints -------------------------------------------------


@app.get("/instances")
def list_instances() -> list[str]:
    return _instances.list_ids()


@app.post(
    "/schemas/{schema_id}/instances",
    response_model=ProcessInstance,
    status_code=201,
)
def post_instantiate(schema_id: str) -> ProcessInstance:
    schema = _get_or_404(schema_id)
    instance = _run_or_409(lambda: exe.instantiate(schema, context=_context))
    _audit.append(
        EventType.INSTANCE_CREATED,
        instance.id,
        instance.schema_id,
        schema_version=instance.schema_version,
    )
    if instance.state is InstanceState.COMPLETED:
        _audit.append(
            EventType.INSTANCE_COMPLETED,
            instance.id,
            instance.schema_id,
            schema_version=instance.schema_version,
        )
    return instance


@app.get("/instances/{instance_id}", response_model=ProcessInstance)
def get_instance(instance_id: str) -> ProcessInstance:
    return _get_instance_or_404(instance_id)


@app.get("/instances/{instance_id}/worklist", response_model=WorklistReport)
def get_worklist(instance_id: str) -> WorklistReport:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    return WorklistReport(
        state=instance.state.value,
        ready_activities=exe.worklist(instance, schema),
        pending_decisions=exe.pending_decisions(instance, schema),
    )


@app.get("/instances/{instance_id}/tasks", response_model=list[OpenTask])
def get_instance_tasks(instance_id: str) -> list[OpenTask]:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    return assignment.open_tasks(schema, instance)


@app.get("/agents/{agent_id}/tasks", response_model=list[OpenTask])
def get_agent_tasks(agent_id: str) -> list[OpenTask]:
    tasks: list[OpenTask] = []
    for instance_id in _instances.list_ids():
        instance = _instances.get(instance_id)
        if instance is None or instance.state is not InstanceState.RUNNING:
            continue
        schema = _effective_schema_for(instance)
        for task in assignment.open_tasks(schema, instance):
            if agent_id in task.eligible_agents:
                tasks.append(task)
    return tasks


@app.post("/instances/{instance_id}/start", response_model=ProcessInstance)
def post_start_activity(instance_id: str, req: StartActivityRequest) -> ProcessInstance:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    after = _run_or_409(lambda: exe.start_activity(instance, schema, req.node_id))
    _audit.append(
        EventType.ACTIVITY_STARTED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.node_id,
        label=_label_of(schema, req.node_id),
    )
    return after


@app.post("/instances/{instance_id}/complete", response_model=ProcessInstance)
def post_complete_activity(
    instance_id: str, req: CompleteActivityRequest
) -> ProcessInstance:
    before = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(before)
    after = _run_or_409(
        lambda: exe.complete_activity(
            before, schema, req.node_id, req.data, agent_id=req.agent_id, context=_context
        )
    )
    _audit.append(
        EventType.ACTIVITY_COMPLETED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.node_id,
        label=_label_of(schema, req.node_id),
        agent_id=req.agent_id,
    )
    _record_completion(before, after)
    return after


@app.post("/instances/{instance_id}/decide", response_model=ProcessInstance)
def post_decide_branch(instance_id: str, req: DecideBranchRequest) -> ProcessInstance:
    before = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(before)
    after = _run_or_409(
        lambda: exe.decide_branch(
            before, schema, req.node_id, req.target_node_id, context=_context
        )
    )
    _audit.append(
        EventType.BRANCH_DECIDED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.node_id,
        label=_label_of(schema, req.node_id),
        detail={"target_node_id": req.target_node_id},
    )
    _record_completion(before, after)
    return after


# --- ad-hoc changes (per-instance variant; R1/R2) ------------------------


@app.post("/instances/{instance_id}/adhoc/insert", response_model=ProcessInstance)
def post_adhoc_insert(instance_id: str, req: AdhocInsertRequest) -> ProcessInstance:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    after = _commit_instance_or_422(
        lambda: adhoc.adhoc_insert_activity(
            instance, schema, req.after_node_id, req.label, resolver=_resolver
        )
    )
    _audit.append(
        EventType.ADHOC_INSERTED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.after_node_id,
        detail={"label": req.label},
    )
    return after


@app.post("/instances/{instance_id}/adhoc/delete", response_model=ProcessInstance)
def post_adhoc_delete(instance_id: str, req: AdhocDeleteRequest) -> ProcessInstance:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    after = _commit_instance_or_422(
        lambda: adhoc.adhoc_delete_node(
            instance, schema, req.node_id, resolver=_resolver
        )
    )
    _audit.append(
        EventType.ADHOC_DELETED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.node_id,
    )
    return after


# --- schema evolution + instance migration (M1-M5) -----------------------


@app.post("/schemas/{schema_id}/revision", response_model=ProcessSchema)
def post_new_revision(schema_id: str, req: RevisionRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.new_revision(schema, new_schema_id=req.new_schema_id)
    )


@app.post(
    "/instances/{instance_id}/migration-check",
    response_model=MigrationReport,
)
def post_migration_check(
    instance_id: str, req: MigrateRequest
) -> MigrationReport:
    instance = _get_instance_or_404(instance_id)
    source = _get_or_404(instance.schema_id)
    target = _get_or_404(req.target_schema_id)
    findings = migration.check_migration(
        instance,
        source,
        target,
        resolver=_resolver,
        data_mapping=req.data_mapping or None,
    )
    return MigrationReport(migratable=not findings, findings=findings)


@app.post("/instances/{instance_id}/migrate", response_model=ProcessInstance)
def post_migrate(instance_id: str, req: MigrateRequest) -> ProcessInstance:
    instance = _get_instance_or_404(instance_id)
    source = _get_or_404(instance.schema_id)
    target = _get_or_404(req.target_schema_id)
    after = _commit_instance_or_422(
        lambda: migration.migrate_instance(
            instance,
            source,
            target,
            data_mapping=req.data_mapping or None,
            resolver=_resolver,
        )
    )
    _audit.append(
        EventType.INSTANCE_MIGRATED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        detail={
            "source_schema_id": instance.schema_id,
            "target_schema_id": req.target_schema_id,
        },
    )
    return after


# --- monitoring + audit (step 15) ----------------------------------------


@app.get("/instances/{instance_id}/audit", response_model=list[AuditEvent])
def get_instance_audit(instance_id: str) -> list[AuditEvent]:
    _get_instance_or_404(instance_id)
    return instance_timeline(_audit.list_all(), instance_id)


@app.get("/audit", response_model=list[AuditEvent])
def get_audit(
    schema_id: str | None = None, instance_id: str | None = None
) -> list[AuditEvent]:
    events = _audit.list_all()
    if schema_id is not None:
        events = [e for e in events if e.schema_id == schema_id]
    if instance_id is not None:
        events = [e for e in events if e.instance_id == instance_id]
    return events


@app.get("/monitoring/kpis", response_model=KpiReport)
def get_kpis(schema_id: str | None = None) -> KpiReport:
    return compute_kpis(_audit.list_all(), schema_id)


@app.get("/monitoring/process-map", response_model=ProcessMap)
def get_process_map(schema_id: str | None = None) -> ProcessMap:
    return discover_process_map(_audit.list_all(), schema_id)
