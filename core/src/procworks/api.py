# SPDX-License-Identifier: BUSL-1.1
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

import os
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from procworks import adhoc, assignment, metrics, migration
from procworks import bpmn as bpmn_io
from procworks import execution as exe
from procworks import operations as ops
from procworks import org as org_ops
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
from procworks.auth import (
    AuthError,
    OpenAuthBackend,
    Principal,
    create_auth_backend,
)
from procworks.auth_password import (
    PasswordAuthBackend,
    PasswordPolicyError,
    UserView,
    user_view,
)
from procworks.bpmn import BpmnError
from procworks.execution import ExecutionError
from procworks.metrics import ModelReport
from procworks.model import (
    AccessMode,
    ConnectorKind,
    DataType,
    ExecutorKind,
    FollowUpMode,
    FollowUpTrigger,
    ImpactUrgency,
    InstanceState,
    LifecycleState,
    OrgModel,
    ProcessInstance,
    ProcessSchema,
    StaffRule,
    TemplateParameter,
    TimeConstraint,
    ValueClass,
    WorkItemPriority,
)
from procworks.store import (
    create_instance_store,
    create_org_store,
    create_store,
    dehydrate_org,
    hydrate_org,
    make_org_resolver,
    make_resolver,
)
from procworks.validator import CorrectnessError, ValidationFinding, validate

app = FastAPI(
    title="Process-Core API",
    version="0.1.0",
    summary="Headless, block-structured process engine kernel (Correctness by Construction).",
)

# The browser-based UI (Section 8) is a thin web client that may be served from
# a different origin (file:// or a static dev server). It holds no correctness
# logic, so a permissive CORS policy is safe for this local kernel: every
# request still passes the same validate-before-commit path. In production,
# ``PROCWORKS_CORS_ORIGINS`` (comma-separated) pins the allowed origins.
def _cors_origins() -> list[str]:
    raw = os.environ.get("PROCWORKS_CORS_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = create_store()
_instances = create_instance_store()
_org_store = create_org_store()
_resolver = make_resolver(_store)
_org_resolver = make_org_resolver(_org_store)
_context = exe.ExecutionContext(_resolver, _instances)
_audit = create_audit_log()

# Auth is a coarse boundary layer (Auth concept, Variant C). The backend is
# swapped via ``PROCWORKS_AUTH``; the default open backend grants every role and
# leaves ``agent_id`` unbound, so existing clients/tests keep working unchanged.
_auth_backend = create_auth_backend()


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: the verified identity behind the request (401)."""

    try:
        return _auth_backend.authenticate(request.headers.get("Authorization"))
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(*allowed: str) -> Callable[[Principal], Principal]:
    """Build a dependency that admits only principals holding one of ``allowed``.

    This is the *coarse* gate at the boundary; the fine-grained BZR eligibility
    in the core is unaffected and still decides who may actually work a node.
    """

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="forbidden")
        return principal

    return _dep


# Reusable role gates (see Auth concept 3.4). ``viewer`` is the read floor that
# every authenticated role clears; writes need modeler/operator/admin. The
# ``modeler`` is also a runtime actor: they may work tasks and drive execution
# (including testing their own draft schemas), so they share the ``_run`` gate.
_read = Depends(require_role("viewer", "operator", "modeler", "admin"))
_model = Depends(require_role("modeler", "admin"))
_run = Depends(require_role("operator", "modeler", "admin"))
_admin = Depends(require_role("admin"))


def _auth_mode() -> str:
    """Report the active auth backend kind for the client's login UI."""

    if isinstance(_auth_backend, PasswordAuthBackend):
        return "password"
    if isinstance(_auth_backend, OpenAuthBackend):
        return "open"
    return "token"


def _password_backend() -> PasswordAuthBackend:
    """Return the active password backend or 404 when password login is off."""

    if not isinstance(_auth_backend, PasswordAuthBackend):
        raise HTTPException(status_code=404, detail="password login is not enabled")
    return _auth_backend


def _find_agent_name(agent_id: str) -> str | None:
    """Best-effort lookup of an agent's display name across all known models.

    Scans the shared org registry and every (hydrated) schema's org model, so a
    user can be provisioned from an existing agent regardless of where that
    agent is modelled.
    """

    for org_id in _org_store.list_ids():
        org = _org_store.get(org_id)
        if org is not None and agent_id in org.agents:
            return org.agents[agent_id].name
    for schema_id in _store.list_ids():
        schema = _get_or_404(schema_id)
        agents = (schema.org_model or OrgModel()).agents
        if agent_id in agents:
            return agents[agent_id].name
    return None



def _resolve_acting_agent(principal: Principal, requested: str | None) -> str | None:
    """Pick the acting agent id, never trusting the request body over identity.

    A *bound* principal (token/JWT) acts only as itself: a divergent
    ``req.agent_id`` is rejected (403). An *unbound* principal (open dev mode)
    falls back to the requested id so the quickstart keeps working -- the core
    BZR check still rejects an ineligible agent with 409.
    """

    if principal.is_bound:
        if requested is not None and requested != principal.agent_id:
            raise HTTPException(
                status_code=403, detail="cannot act on behalf of another agent"
            )
        return principal.agent_id
    return requested


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


class AuthConfig(BaseModel):
    mode: str = Field(..., examples=["password"])
    password_login: bool = False


class LoginRequest(BaseModel):
    login: str = Field(..., examples=["erika.musterfrau"])
    password: str = Field(..., examples=["geheim"])


class LoginResponse(BaseModel):
    token: str
    principal: Principal
    must_change: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    roles: list[str] = Field(..., examples=[["operator"]])
    agent_id: str | None = Field(default=None, examples=["a1"])
    login: str | None = Field(default=None, examples=["erika.musterfrau"])
    display_name: str | None = Field(default=None, examples=["Erika Musterfrau"])


class CreateUserResponse(BaseModel):
    user: UserView
    login: str
    initial_password: str


class ResetPasswordResponse(BaseModel):
    login: str
    initial_password: str


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


class RenameNodeRequest(BaseModel):
    label: str = Field(..., examples=["Antrag genehmigen"])


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


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, examples=["Erika Mustermann"])
    role_ids: list[str] | None = Field(default=None, examples=[["sb"]])
    org_unit_id: str | None = Field(default=None, examples=["einkauf"])


class SetManagerRequest(BaseModel):
    manager_id: str | None = Field(default=None, examples=["a1"])


class SetParentRequest(BaseModel):
    parent_id: str | None = Field(default=None, examples=["unit_1"])


class SetDeputyRequest(BaseModel):
    deputy_id: str | None = Field(default=None, examples=["a2"])


class CreateOrgModelRequest(BaseModel):
    name: str = Field(..., examples=["Stadtverwaltung"])
    org_model_id: str | None = Field(default=None, examples=["org_city"])


class LinkOrgModelRequest(BaseModel):
    org_model_id: str = Field(..., examples=["org_city"])


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


class SetValueClassRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    value_class: ValueClass | None = Field(
        default=None, examples=[ValueClass.VALUE_ADDING]
    )


class SetPriorityRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    #: When ``None`` the priority annotation is cleared.
    priority: WorkItemPriority | None = Field(
        default=None,
        examples=[
            WorkItemPriority(impact=ImpactUrgency.HIGH, urgency=ImpactUrgency.HIGH)
        ],
    )


class SetTimeConstraintRequest(BaseModel):
    node_id: str = Field(..., examples=["act_1"])
    #: When ``None`` the temporal annotation is cleared.
    constraint: TimeConstraint | None = Field(
        default=None, examples=[TimeConstraint(max_duration_seconds=3600)]
    )


class SetDeadlineRequest(BaseModel):
    deadline_seconds: float | None = Field(default=None, examples=[86400])


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
    return hydrate_org(schema, _org_resolver)


def _persist_schema(schema: ProcessSchema) -> ProcessSchema:
    """Store a schema, clearing hydrated shared-org data first (single source)."""

    _store.put(dehydrate_org(schema))
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
    return _persist_schema(schema)


def _get_org_or_404(org_id: str) -> OrgModel:
    org = _org_store.get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail=f"org model '{org_id}' not found")
    return org


def _schemas_referencing(org_id: str) -> list[ProcessSchema]:
    """All stored schemas that resolve their staffing against this shared org."""

    result: list[ProcessSchema] = []
    for sid in _store.list_ids():
        schema = _store.get(sid)
        if schema is not None and schema.org_model_id == org_id:
            result.append(schema)
    return result


def _commit_org_or_422(result_fn: object) -> OrgModel:
    """Apply a shared-org change, re-validating every referencing schema.

    The org op is validated for internal consistency (validate-before-commit);
    additionally each schema that references the org is hydrated with the
    *candidate* org and re-validated, so an org edit can never silently break a
    referencing process's staffing. Only if every referencing schema stays
    correct is the new org persisted (atomic across the org boundary).
    """

    try:
        org = result_fn()  # type: ignore[operator]
    except CorrectnessError as exc:
        raise HTTPException(
            status_code=422,
            detail={"findings": [f.model_dump() for f in exc.findings]},
        ) from exc
    if org.id is not None:
        breaking: list[ValidationFinding] = []
        for schema in _schemas_referencing(org.id):
            hydrated = schema.model_copy(update={"org_model": org.model_copy(deep=True)})
            breaking += validate(hydrated, _resolver)
        if breaking:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "org change would break referencing schemas",
                    "findings": [f.model_dump() for f in breaking],
                },
            )
    return _org_store.put(org)


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
    return hydrate_org(adhoc.effective_schema(instance, base), _org_resolver)


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


@app.get("/auth/me", response_model=Principal)
def get_me(principal: Principal = Depends(get_principal)) -> Principal:
    """Return the verified identity of the caller (for the client's login UI)."""

    return principal


@app.get("/auth/config", response_model=AuthConfig)
def get_auth_config() -> AuthConfig:
    """Public: tell the client which login UI to render (open/token/password)."""

    mode = _auth_mode()
    return AuthConfig(mode=mode, password_login=mode == "password")


@app.post("/auth/login", response_model=LoginResponse)
def post_login(req: LoginRequest) -> LoginResponse:
    """Exchange username + password for a session bearer token (password mode)."""

    backend = _password_backend()
    try:
        result = backend.login(req.login, req.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=401, detail=exc.message, headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    return LoginResponse(
        token=result.token,
        principal=result.principal,
        must_change=result.must_change,
    )


@app.post("/auth/logout", status_code=204)
def post_logout(request: Request) -> Response:
    """Invalidate the caller's current session token (password mode)."""

    backend = _password_backend()
    backend.logout(request.headers.get("Authorization"))
    return Response(status_code=204)


@app.post("/auth/change-password", status_code=204)
def post_change_password(
    req: ChangePasswordRequest,
    principal: Principal = Depends(get_principal),
) -> Response:
    """Self-service password change; clears the forced-change flag."""

    backend = _password_backend()
    try:
        backend.change_password(
            principal.subject, req.current_password, req.new_password
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@app.get("/users", response_model=list[UserView], dependencies=[_admin])
def list_users() -> list[UserView]:
    """List login users (admin only); never exposes password hashes."""

    backend = _password_backend()
    return [user_view(u) for u in backend.store.list_users()]


@app.post("/users", response_model=CreateUserResponse, status_code=201, dependencies=[_admin])
def create_user(req: CreateUserRequest) -> CreateUserResponse:
    """Provision a login from an agent; returns the initial password once (admin)."""

    backend = _password_backend()
    display_name = req.display_name
    if display_name is None and req.agent_id is not None:
        display_name = _find_agent_name(req.agent_id)
    subject = req.login or display_name or req.agent_id
    if not subject:
        raise HTTPException(
            status_code=400, detail="need login, display_name or agent_id"
        )
    try:
        user, initial_password = backend.create_user(
            subject=subject,
            roles=req.roles,
            agent_id=req.agent_id,
            login=req.login,
            display_name=display_name,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateUserResponse(
        user=user_view(user),
        login=user.login,
        initial_password=initial_password,
    )


@app.post(
    "/users/{login}/reset-password",
    response_model=ResetPasswordResponse,
    dependencies=[_admin],
)
def reset_user_password(login: str) -> ResetPasswordResponse:
    """Set a fresh initial password (forces change); returns it once (admin)."""

    backend = _password_backend()
    try:
        initial_password = backend.reset_password(login)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return ResetPasswordResponse(login=login, initial_password=initial_password)


@app.delete("/users/{login}", status_code=204, dependencies=[_admin])
def delete_user(login: str) -> Response:
    """Remove a login user (admin only)."""

    backend = _password_backend()
    backend.store.delete_user(login)
    return Response(status_code=204)


@app.get("/schemas", dependencies=[_read])
def list_schemas() -> list[str]:
    return _store.list_ids()


@app.post(
    "/schemas", response_model=ProcessSchema, status_code=201, dependencies=[_model]
)
def create_schema(req: CreateSchemaRequest) -> ProcessSchema:
    return _commit_or_422(lambda: ops.create_empty_schema(req.name))


@app.get("/schemas/{schema_id}", response_model=ProcessSchema, dependencies=[_read])
def get_schema(schema_id: str) -> ProcessSchema:
    return _get_or_404(schema_id)


@app.get(
    "/schemas/{schema_id}/validation",
    response_model=ValidationReport,
    dependencies=[_read],
)
def get_validation(schema_id: str) -> ValidationReport:
    schema = _get_or_404(schema_id)
    findings = validate(schema, _resolver)
    return ValidationReport(correct=not findings, findings=findings)


@app.get(
    "/schemas/{schema_id}/metrics",
    response_model=ModelReport,
    dependencies=[_read],
)
def get_metrics(schema_id: str) -> ModelReport:
    """Read-only model metrics, 7PMG hints and value-class mix (roadmap E7/E3).

    These figures are advisory only and never affect Stufe-A/B correctness.
    """

    schema = _get_or_404(schema_id)
    return metrics.model_report(schema)


@app.post(
    "/schemas/{schema_id}/serial-insert",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_serial_insert(schema_id: str, req: SerialInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.serial_insert(schema, req.label, req.after_node_id))


@app.post(
    "/schemas/{schema_id}/parallel-insert",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_parallel_insert(schema_id: str, req: ParallelInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.parallel_insert(schema, req.branch_labels, req.after_node_id)
    )


@app.post(
    "/schemas/{schema_id}/conditional-insert",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_conditional_insert(schema_id: str, req: ConditionalInsertRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    branches = [(b.condition, b.label) for b in req.branches]
    return _commit_or_422(lambda: ops.conditional_insert(schema, branches, req.after_node_id))


@app.patch(
    "/schemas/{schema_id}/nodes/{node_id}",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def patch_rename_node(
    schema_id: str, node_id: str, req: RenameNodeRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.rename_node(schema, node_id, req.label))


@app.delete(
    "/schemas/{schema_id}/nodes/{node_id}",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def delete_schema_node(schema_id: str, node_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.delete_node(schema, node_id))


@app.post(
    "/schemas/{schema_id}/data-elements",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_add_data_element(schema_id: str, req: AddDataElementRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_data_element(schema, req.name, req.data_type, req.element_id)
    )


@app.post(
    "/schemas/{schema_id}/data-access",
    response_model=ProcessSchema,
    dependencies=[_model],
)
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


@app.post(
    "/schemas/{schema_id}/connectors",
    response_model=ProcessSchema,
    dependencies=[_model],
)
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
    dependencies=[_model],
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


@app.get("/schemas/{schema_id}/bpmn", dependencies=[_read])
def get_export_bpmn(schema_id: str) -> Response:
    schema = _get_or_404(schema_id)
    return Response(content=bpmn_io.export_bpmn(schema), media_type="application/xml")


@app.post(
    "/bpmn-import",
    response_model=ProcessSchema,
    status_code=201,
    dependencies=[_model],
)
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


# --- shared, cross-schema organisation models ---------------------------


@app.get("/org-models", response_model=list[OrgModel], dependencies=[_read])
def get_org_models() -> list[OrgModel]:
    return [org for oid in _org_store.list_ids() if (org := _org_store.get(oid)) is not None]


@app.post(
    "/org-models", response_model=OrgModel, status_code=201, dependencies=[_admin]
)
def post_create_org_model(req: CreateOrgModelRequest) -> OrgModel:
    org = org_ops.create_org_model(req.name, org_id=req.org_model_id)
    return _org_store.put(org)


@app.get("/org-models/{org_id}", response_model=OrgModel, dependencies=[_read])
def get_org_model(org_id: str) -> OrgModel:
    return _get_org_or_404(org_id)


@app.post("/org-models/{org_id}/roles", response_model=OrgModel, dependencies=[_admin])
def post_org_add_role(org_id: str, req: AddRoleRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(lambda: org_ops.org_add_role(org, req.name, role_id=req.role_id))


@app.post(
    "/org-models/{org_id}/org-units", response_model=OrgModel, dependencies=[_admin]
)
def post_org_add_unit(org_id: str, req: AddOrgUnitRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(
        lambda: org_ops.org_add_unit(
            org,
            req.name,
            parent_id=req.parent_id,
            org_unit_id=req.org_unit_id,
            manager_id=req.manager_id,
        )
    )


@app.post(
    "/org-models/{org_id}/org-units/{org_unit_id}/manager",
    response_model=OrgModel,
    dependencies=[_admin],
)
def post_org_set_manager(org_id: str, org_unit_id: str, req: SetManagerRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(lambda: org_ops.org_set_manager(org, org_unit_id, req.manager_id))


@app.post(
    "/org-models/{org_id}/org-units/{org_unit_id}/parent",
    response_model=OrgModel,
    dependencies=[_admin],
)
def post_org_set_parent(org_id: str, org_unit_id: str, req: SetParentRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(lambda: org_ops.org_set_parent(org, org_unit_id, req.parent_id))


@app.post("/org-models/{org_id}/agents", response_model=OrgModel, dependencies=[_admin])
def post_org_add_agent(org_id: str, req: AddAgentRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(
        lambda: org_ops.org_add_agent(
            org,
            req.name,
            role_ids=req.role_ids,
            org_unit_id=req.org_unit_id,
            agent_id=req.agent_id,
            deputy_id=req.deputy_id,
        )
    )


@app.patch(
    "/org-models/{org_id}/agents/{agent_id}",
    response_model=OrgModel,
    dependencies=[_admin],
)
def patch_org_update_agent(org_id: str, agent_id: str, req: UpdateAgentRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    org_unit = req.org_unit_id if "org_unit_id" in req.model_fields_set else org_ops.KEEP
    return _commit_org_or_422(
        lambda: org_ops.org_update_agent(
            org, agent_id, name=req.name, role_ids=req.role_ids, org_unit_id=org_unit
        )
    )


@app.post(
    "/org-models/{org_id}/agents/{agent_id}/deputy",
    response_model=OrgModel,
    dependencies=[_admin],
)
def post_org_set_deputy(org_id: str, agent_id: str, req: SetDeputyRequest) -> OrgModel:
    org = _get_org_or_404(org_id)
    return _commit_org_or_422(lambda: org_ops.org_set_deputy(org, agent_id, req.deputy_id))


@app.post(
    "/schemas/{schema_id}/org-model",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_link_org_model(schema_id: str, req: LinkOrgModelRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    org = _get_org_or_404(req.org_model_id)
    return _commit_or_422(lambda: ops.link_org_model(schema, req.org_model_id, org))


@app.delete(
    "/schemas/{schema_id}/org-model",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def delete_unlink_org_model(schema_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.unlink_org_model(schema))


@app.post("/schemas/{schema_id}/roles", response_model=ProcessSchema, dependencies=[_model])
def post_add_role(schema_id: str, req: AddRoleRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.add_role(schema, req.name, req.role_id))


@app.post(
    "/schemas/{schema_id}/org-units", response_model=ProcessSchema, dependencies=[_model]
)
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
    dependencies=[_model],
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
    dependencies=[_model],
)
def post_set_org_unit_parent(
    schema_id: str, org_unit_id: str, req: SetParentRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_org_unit_parent(schema, org_unit_id, req.parent_id)
    )


@app.post("/schemas/{schema_id}/agents", response_model=ProcessSchema, dependencies=[_model])
def post_add_agent(schema_id: str, req: AddAgentRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.add_agent(
            schema, req.name, req.role_ids, req.org_unit_id, req.agent_id, req.deputy_id
        )
    )


@app.patch(
    "/schemas/{schema_id}/agents/{agent_id}",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def patch_update_agent(
    schema_id: str, agent_id: str, req: UpdateAgentRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    # Distinguish "org_unit_id omitted" (keep) from "org_unit_id: null" (detach).
    org_unit = req.org_unit_id if "org_unit_id" in req.model_fields_set else ops.KEEP
    return _commit_or_422(
        lambda: ops.update_agent(
            schema, agent_id, name=req.name, role_ids=req.role_ids, org_unit_id=org_unit
        )
    )


@app.post(
    "/schemas/{schema_id}/agents/{agent_id}/deputy",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_set_agent_deputy(
    schema_id: str, agent_id: str, req: SetDeputyRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_agent_deputy(schema, agent_id, req.deputy_id)
    )


@app.post(
    "/schemas/{schema_id}/activity-templates",
    response_model=ProcessSchema,
    dependencies=[_model],
)
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


@app.post("/schemas/{schema_id}/service", response_model=ProcessSchema, dependencies=[_model])
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


@app.post("/schemas/{schema_id}/staff-rule", response_model=ProcessSchema, dependencies=[_model])
def post_assign_staff_rule(schema_id: str, req: AssignStaffRuleRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.assign_staff_rule(schema, req.node_id, req.rule))


@app.post(
    "/schemas/{schema_id}/value-class",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_set_value_class(schema_id: str, req: SetValueClassRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_value_class(schema, req.node_id, req.value_class)
    )


@app.post(
    "/schemas/{schema_id}/priority",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_set_priority(schema_id: str, req: SetPriorityRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_node_priority(schema, req.node_id, req.priority)
    )


@app.post(
    "/schemas/{schema_id}/time-constraint",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_set_time_constraint(
    schema_id: str, req: SetTimeConstraintRequest
) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.set_time_constraint(schema, req.node_id, req.constraint)
    )


@app.post(
    "/schemas/{schema_id}/deadline",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def post_set_deadline(schema_id: str, req: SetDeadlineRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.set_deadline(schema, req.deadline_seconds))


@app.post("/schemas/{schema_id}/subprocess", response_model=ProcessSchema, dependencies=[_model])
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


@app.post(
    "/schemas/{schema_id}/subprocess-mapping",
    response_model=ProcessSchema,
    dependencies=[_model],
)
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


@app.post("/schemas/{schema_id}/follow-up", response_model=ProcessSchema, dependencies=[_model])
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


@app.delete(
    "/schemas/{schema_id}/follow-up/{link_id}",
    response_model=ProcessSchema,
    dependencies=[_model],
)
def delete_follow_up(schema_id: str, link_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.unlink_follow_up(schema, link_id))


@app.post("/schemas/{schema_id}/release", response_model=ProcessSchema, dependencies=[_model])
def post_release(schema_id: str) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(lambda: ops.release(schema, _resolver))


# --- execution endpoints -------------------------------------------------


@app.get("/instances", dependencies=[_read])
def list_instances() -> list[str]:
    return _instances.list_ids()


@app.post(
    "/schemas/{schema_id}/instances",
    response_model=ProcessInstance,
    status_code=201,
)
def post_instantiate(
    schema_id: str, principal: Principal = Depends(get_principal)
) -> ProcessInstance:
    """Start an instance of a schema.

    A RELEASED schema may be instantiated for real by operator/modeler/admin.
    A non-released (draft) schema may only be started as a throw-away *test*
    instance, and only by a modeller/admin -- it is flagged ``is_test`` and no
    audit events are recorded, so it never pollutes the monitoring KPIs.
    """

    schema = _get_or_404(schema_id)
    released = schema.lifecycle_state is LifecycleState.RELEASED
    if released:
        if not principal.roles.intersection({"operator", "modeler", "admin"}):
            raise HTTPException(status_code=403, detail="forbidden")
    elif not principal.roles.intersection({"modeler", "admin"}):
        raise HTTPException(
            status_code=403,
            detail="only modellers/admins may start a test instance of a draft",
        )
    is_test = not released
    instance = _run_or_409(
        lambda: exe.instantiate(
            schema, context=_context, allow_unreleased=not released, is_test=is_test
        )
    )
    if is_test:
        # Test instances stay out of the audit log (and therefore the KPIs).
        return instance
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


@app.get("/instances/{instance_id}", response_model=ProcessInstance, dependencies=[_read])
def get_instance(instance_id: str) -> ProcessInstance:
    return _get_instance_or_404(instance_id)


@app.get(
    "/instances/{instance_id}/worklist",
    response_model=WorklistReport,
    dependencies=[_read],
)
def get_worklist(instance_id: str) -> WorklistReport:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    return WorklistReport(
        state=instance.state.value,
        ready_activities=exe.worklist(instance, schema),
        pending_decisions=exe.pending_decisions(instance, schema),
    )


@app.get(
    "/instances/{instance_id}/tasks",
    response_model=list[OpenTask],
    dependencies=[_read],
)
def get_instance_tasks(instance_id: str) -> list[OpenTask]:
    instance = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(instance)
    return assignment.open_tasks(schema, instance)


def _tasks_for_agent(agent_id: str) -> list[OpenTask]:
    """Collect the open tasks an agent is currently eligible for (incl. deputy)."""

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


@app.get("/me/tasks", response_model=list[OpenTask])
def get_my_tasks(
    principal: Principal = Depends(require_role("operator", "modeler", "admin")),
) -> list[OpenTask]:
    """The worklist of the logged-in agent (the bound principal's own tasks)."""

    if principal.agent_id is None:
        # Open dev mode: no bound agent -> use /agents/{id}/tasks with a picker.
        return []
    return _tasks_for_agent(principal.agent_id)


@app.get("/agents/{agent_id}/tasks", response_model=list[OpenTask])
def get_agent_tasks(
    agent_id: str,
    principal: Principal = Depends(require_role("operator", "modeler", "admin")),
) -> list[OpenTask]:
    # A bound, non-supervisor operator may only read their own worklist; an
    # admin/modeler may inspect any agent's list (supervision).
    if (
        principal.is_bound
        and principal.agent_id != agent_id
        and not principal.roles.intersection({"admin", "modeler"})
    ):
        raise HTTPException(status_code=403, detail="forbidden")
    return _tasks_for_agent(agent_id)


@app.post("/instances/{instance_id}/start", response_model=ProcessInstance, dependencies=[_run])
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
    instance_id: str,
    req: CompleteActivityRequest,
    principal: Principal = Depends(require_role("operator", "modeler", "admin")),
) -> ProcessInstance:
    before = _get_instance_or_404(instance_id)
    schema = _effective_schema_for(before)
    acting_agent = _resolve_acting_agent(principal, req.agent_id)
    after = _run_or_409(
        lambda: exe.complete_activity(
            before, schema, req.node_id, req.data, agent_id=acting_agent, context=_context
        )
    )
    _audit.append(
        EventType.ACTIVITY_COMPLETED,
        after.id,
        after.schema_id,
        schema_version=after.schema_version,
        node_id=req.node_id,
        label=_label_of(schema, req.node_id),
        agent_id=acting_agent,
    )
    _record_completion(before, after)
    return after


@app.post("/instances/{instance_id}/decide", response_model=ProcessInstance)
def post_decide_branch(
    instance_id: str,
    req: DecideBranchRequest,
    principal: Principal = Depends(require_role("operator", "modeler", "admin")),
) -> ProcessInstance:
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


@app.post(
    "/instances/{instance_id}/adhoc/insert",
    response_model=ProcessInstance,
    dependencies=[_run],
)
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


@app.post(
    "/instances/{instance_id}/adhoc/delete",
    response_model=ProcessInstance,
    dependencies=[_run],
)
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


@app.post("/schemas/{schema_id}/revision", response_model=ProcessSchema, dependencies=[_model])
def post_new_revision(schema_id: str, req: RevisionRequest) -> ProcessSchema:
    schema = _get_or_404(schema_id)
    return _commit_or_422(
        lambda: ops.new_revision(schema, new_schema_id=req.new_schema_id)
    )


@app.post(
    "/instances/{instance_id}/migration-check",
    response_model=MigrationReport,
    dependencies=[_run],
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


@app.post("/instances/{instance_id}/migrate", response_model=ProcessInstance, dependencies=[_run])
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


@app.get(
    "/instances/{instance_id}/audit",
    response_model=list[AuditEvent],
    dependencies=[_read],
)
def get_instance_audit(instance_id: str) -> list[AuditEvent]:
    _get_instance_or_404(instance_id)
    return instance_timeline(_audit.list_all(), instance_id)


@app.get("/audit", response_model=list[AuditEvent], dependencies=[_read])
def get_audit(
    schema_id: str | None = None, instance_id: str | None = None
) -> list[AuditEvent]:
    events = _audit.list_all()
    if schema_id is not None:
        events = [e for e in events if e.schema_id == schema_id]
    if instance_id is not None:
        events = [e for e in events if e.instance_id == instance_id]
    return events


@app.get("/monitoring/kpis", response_model=KpiReport, dependencies=[_read])
def get_kpis(schema_id: str | None = None) -> KpiReport:
    return compute_kpis(_audit.list_all(), schema_id)


@app.get("/monitoring/process-map", response_model=ProcessMap, dependencies=[_read])
def get_process_map(schema_id: str | None = None) -> ProcessMap:
    return discover_process_map(_audit.list_all(), schema_id)
