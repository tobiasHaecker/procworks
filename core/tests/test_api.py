# SPDX-License-Identifier: BUSL-1.1
"""API tests using FastAPI's TestClient (httpx-based)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from procworks.api import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_build_schema_via_api() -> None:
    resp = client.post("/schemas", json={"name": "Urlaubsantrag"})
    assert resp.status_code == 201
    schema = resp.json()
    sid = schema["id"]
    assert schema["lifecycle_state"] == "ENTWURF"

    resp = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Antrag prüfen", "after_node_id": "start"},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/schemas/{sid}/conditional-insert",
        json={
            "after_node_id": "start",
            "branches": [
                {"condition": "betrag > 1000", "label": "Freigabe Leitung"},
                {"condition": "betrag <= 1000", "label": "Freigabe Team"},
            ],
        },
    )
    assert resp.status_code == 200

    resp = client.get(f"/schemas/{sid}/validation")
    assert resp.status_code == 200
    assert resp.json()["correct"] is True


def test_invalid_operation_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "X"}).json()["id"]
    resp = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "X", "after_node_id": "end"},
    )
    assert resp.status_code == 422
    assert "findings" in resp.json()["detail"]


def test_rename_and_delete_node_via_api() -> None:
    sid = client.post("/schemas", json={"name": "Bearbeiten"}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "Alt", "after_node_id": "start"})
    schema = client.get(f"/schemas/{sid}").json()
    act_id = next(nid for nid, n in schema["nodes"].items() if n["type"] == "ACTIVITY")

    resp = client.patch(f"/schemas/{sid}/nodes/{act_id}", json={"label": "Neu"})
    assert resp.status_code == 200
    assert resp.json()["nodes"][act_id]["label"] == "Neu"

    resp = client.delete(f"/schemas/{sid}/nodes/{act_id}")
    assert resp.status_code == 200
    assert act_id not in resp.json()["nodes"]
    assert client.get(f"/schemas/{sid}/validation").json()["correct"] is True


def test_delete_join_via_api_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "JoinDel"}).json()["id"]
    client.post(
        f"/schemas/{sid}/parallel-insert",
        json={"branch_labels": ["A", "B"], "after_node_id": "start"},
    )
    schema = client.get(f"/schemas/{sid}").json()
    join_id = next(nid for nid, n in schema["nodes"].items() if n["type"] == "AND_JOIN")
    resp = client.delete(f"/schemas/{sid}/nodes/{join_id}")
    assert resp.status_code == 422
    assert "findings" in resp.json()["detail"]


def test_delete_split_via_api_removes_block() -> None:
    sid = client.post("/schemas", json={"name": "BlockDel"}).json()["id"]
    client.post(
        f"/schemas/{sid}/parallel-insert",
        json={"branch_labels": ["A", "B"], "after_node_id": "start"},
    )
    schema = client.get(f"/schemas/{sid}").json()
    split_id = next(nid for nid, n in schema["nodes"].items() if n["type"] == "AND_SPLIT")
    resp = client.delete(f"/schemas/{sid}/nodes/{split_id}")
    assert resp.status_code == 200
    types = {n["type"] for n in resp.json()["nodes"].values()}
    assert types == {"START", "END"}


def test_release_via_api_then_immutable() -> None:
    sid = client.post("/schemas", json={"name": "R"}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "S", "after_node_id": "start"})
    resp = client.post(f"/schemas/{sid}/release")
    assert resp.status_code == 200
    assert resp.json()["lifecycle_state"] == "RELEASED"

    resp = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Y", "after_node_id": "start"},
    )
    assert resp.status_code == 422


def test_unknown_schema_returns_404() -> None:
    resp = client.get("/schemas/nope")
    assert resp.status_code == 404


def test_data_flow_via_api() -> None:
    sid = client.post("/schemas", json={"name": "Daten"}).json()["id"]
    writer = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Erfassen", "after_node_id": "start"},
    ).json()
    writer_id = next(n["id"] for n in writer["nodes"].values() if n["label"] == "Erfassen")
    reader = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Pruefen", "after_node_id": writer_id},
    ).json()
    reader_id = next(n["id"] for n in reader["nodes"].values() if n["label"] == "Pruefen")

    resp = client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "betrag", "data_type": "FLOAT", "element_id": "betrag"},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/schemas/{sid}/data-access",
        json={"node_id": writer_id, "element_id": "betrag", "mode": "WRITE"},
    )
    assert resp.status_code == 200
    resp = client.post(
        f"/schemas/{sid}/data-access",
        json={"node_id": reader_id, "element_id": "betrag", "mode": "READ"},
    )
    assert resp.status_code == 200
    assert client.get(f"/schemas/{sid}/validation").json()["correct"] is True


def test_data_flow_read_before_write_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "D1"}).json()["id"]
    schema = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Liest", "after_node_id": "start"},
    ).json()
    reader_id = next(n["id"] for n in schema["nodes"].values() if n["label"] == "Liest")
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "x", "data_type": "INTEGER", "element_id": "x"},
    )
    resp = client.post(
        f"/schemas/{sid}/data-access",
        json={"node_id": reader_id, "element_id": "x", "mode": "READ"},
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "D1" in rules


def test_staff_rule_via_api() -> None:
    sid = client.post("/schemas", json={"name": "BZR"}).json()["id"]
    schema = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Bearbeiten", "after_node_id": "start"},
    ).json()
    act_id = next(n["id"] for n in schema["nodes"].values() if n["label"] == "Bearbeiten")

    client.post(f"/schemas/{sid}/roles", json={"name": "Sachbearbeiter", "role_id": "sb"})
    client.post(
        f"/schemas/{sid}/agents",
        json={"name": "Erika", "role_ids": ["sb"], "agent_id": "a1"},
    )
    resp = client.post(
        f"/schemas/{sid}/staff-rule",
        json={"node_id": act_id, "rule": {"kind": "ROLE", "ref": "sb"}},
    )
    assert resp.status_code == 200
    assert client.get(f"/schemas/{sid}/validation").json()["correct"] is True


def test_update_agent_via_api() -> None:
    sid = client.post("/schemas", json={"name": "EditAgent"}).json()["id"]
    client.post(f"/schemas/{sid}/roles", json={"name": "Sachbearbeiter", "role_id": "sb"})
    client.post(f"/schemas/{sid}/roles", json={"name": "Manager", "role_id": "mgr"})
    client.post(
        f"/schemas/{sid}/org-units", json={"name": "Einkauf", "org_unit_id": "einkauf"}
    )
    client.post(
        f"/schemas/{sid}/agents",
        json={
            "name": "Erika",
            "role_ids": ["sb"],
            "org_unit_id": "einkauf",
            "agent_id": "a1",
        },
    )

    # Rename + change roles; org unit omitted -> kept.
    resp = client.patch(
        f"/schemas/{sid}/agents/a1",
        json={"name": "Erika Mustermann", "role_ids": ["mgr"]},
    )
    assert resp.status_code == 200
    agent = resp.json()["org_model"]["agents"]["a1"]
    assert agent["name"] == "Erika Mustermann"
    assert agent["role_ids"] == ["mgr"]
    assert agent["org_unit_id"] == "einkauf"

    # Explicit null detaches the org unit.
    resp = client.patch(f"/schemas/{sid}/agents/a1", json={"org_unit_id": None})
    assert resp.status_code == 200
    assert resp.json()["org_model"]["agents"]["a1"]["org_unit_id"] is None


def test_update_unknown_agent_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "EditNoAgent"}).json()["id"]
    resp = client.patch(f"/schemas/{sid}/agents/ghost", json={"name": "X"})
    assert resp.status_code == 422
    assert "findings" in resp.json()["detail"]


def test_staff_rule_unknown_role_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "BZRbad"}).json()["id"]
    schema = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Bearbeiten", "after_node_id": "start"},
    ).json()
    act_id = next(n["id"] for n in schema["nodes"].values() if n["label"] == "Bearbeiten")
    resp = client.post(
        f"/schemas/{sid}/staff-rule",
        json={"node_id": act_id, "rule": {"kind": "ROLE", "ref": "ghost"}},
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "Z1" in rules


def test_instance_run_via_api() -> None:
    sid = client.post("/schemas", json={"name": "Lauf"}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "S", "after_node_id": "start"})
    client.post(f"/schemas/{sid}/release")

    resp = client.post(f"/schemas/{sid}/instances")
    assert resp.status_code == 201
    instance = resp.json()
    iid = instance["id"]
    assert instance["state"] == "RUNNING"

    wl = client.get(f"/instances/{iid}/worklist").json()
    assert len(wl["ready_activities"]) == 1
    node_id = wl["ready_activities"][0]

    resp = client.post(f"/instances/{iid}/complete", json={"node_id": node_id})
    assert resp.status_code == 200
    assert resp.json()["state"] == "COMPLETED"


def test_instantiate_draft_returns_409() -> None:
    sid = client.post("/schemas", json={"name": "NochEntwurf"}).json()["id"]
    resp = client.post(f"/schemas/{sid}/instances")
    assert resp.status_code == 409
    assert "message" in resp.json()["detail"]


def test_subprocess_via_api() -> None:
    # released target schema
    tid = client.post("/schemas", json={"name": "Teilprozess"}).json()["id"]
    client.post(f"/schemas/{tid}/serial-insert", json={"label": "T", "after_node_id": "start"})
    client.post(f"/schemas/{tid}/release")

    pid = client.post("/schemas", json={"name": "Haupt"}).json()["id"]
    resp = client.post(
        f"/schemas/{pid}/subprocess",
        json={"after_node_id": "start", "target_schema_id": tid, "target_version": 1},
    )
    assert resp.status_code == 200
    types = {n["type"] for n in resp.json()["nodes"].values()}
    assert "SUBPROCESS" in types
    assert client.get(f"/schemas/{pid}/validation").json()["correct"] is True


def test_subprocess_unreleased_target_returns_422() -> None:
    tid = client.post("/schemas", json={"name": "Entwurfsziel"}).json()["id"]
    pid = client.post("/schemas", json={"name": "Haupt2"}).json()["id"]
    resp = client.post(
        f"/schemas/{pid}/subprocess",
        json={"after_node_id": "start", "target_schema_id": tid, "target_version": 1},
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "H1" in rules


def test_subprocess_execution_via_api() -> None:
    # released target schema with one activity
    tid = client.post("/schemas", json={"name": "Kindprozess"}).json()["id"]
    client.post(f"/schemas/{tid}/serial-insert", json={"label": "T", "after_node_id": "start"})
    client.post(f"/schemas/{tid}/release")

    # parent with a SUBPROCESS node right after start, then released
    pid = client.post("/schemas", json={"name": "Elternlauf"}).json()["id"]
    client.post(
        f"/schemas/{pid}/subprocess",
        json={"after_node_id": "start", "target_schema_id": tid, "target_version": 1},
    )
    client.post(f"/schemas/{pid}/release")

    inst = client.post(f"/schemas/{pid}/instances").json()
    assert inst["state"] == "RUNNING"
    assert inst["child_instances"]  # the sub-process spawned a child
    child_id = next(iter(inst["child_instances"].values()))

    wl = client.get(f"/instances/{child_id}/worklist").json()
    assert len(wl["ready_activities"]) == 1
    node_id = wl["ready_activities"][0]

    resp = client.post(f"/instances/{child_id}/complete", json={"node_id": node_id})
    assert resp.status_code == 200
    assert resp.json()["state"] == "COMPLETED"

    # completing the child joins back and drives the parent to completion
    parent = client.get(f"/instances/{inst['id']}").json()
    assert parent["state"] == "COMPLETED"


def _released_two_step(name: str) -> str:
    """Create + release a start -> A -> B -> end schema; return its id."""

    sid = client.post("/schemas", json={"name": name}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "B", "after_node_id": "start"})
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "A", "after_node_id": "start"})
    client.post(f"/schemas/{sid}/release")
    return sid


def test_adhoc_insert_via_api_runs_through_variant() -> None:
    sid = _released_two_step("AdhocLauf")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    wl = client.get(f"/instances/{iid}/worklist").json()
    a_id = wl["ready_activities"][0]

    resp = client.post(
        f"/instances/{iid}/adhoc/insert",
        json={"after_node_id": a_id, "label": "Zusatz"},
    )
    assert resp.status_code == 200
    instance = resp.json()
    assert instance["ad_hoc_schema"] is not None
    assert instance["ad_hoc_deltas"]

    # Drive the instance to completion through its variant.
    client.post(f"/instances/{iid}/complete", json={"node_id": a_id})
    while True:
        wl = client.get(f"/instances/{iid}/worklist").json()
        if wl["state"] == "COMPLETED":
            break
        node_id = wl["ready_activities"][0]
        client.post(f"/instances/{iid}/complete", json={"node_id": node_id})
    assert client.get(f"/instances/{iid}").json()["state"] == "COMPLETED"


def test_adhoc_insert_after_executed_node_returns_422() -> None:
    sid = _released_two_step("AdhocFehler")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    resp = client.post(
        f"/instances/{iid}/adhoc/insert",
        json={"after_node_id": "start", "label": "ZuSpaet"},
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "R1" in rules


def test_revision_via_api_bumps_version() -> None:
    sid = _released_two_step("Revision")
    resp = client.post(f"/schemas/{sid}/revision", json={})
    assert resp.status_code == 200
    revision = resp.json()
    assert revision["id"] != sid
    assert revision["version"] == 2
    assert revision["lifecycle_state"] == "ENTWURF"


def test_migration_check_and_migrate_via_api() -> None:
    sid = _released_two_step("MigrationQuelle")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    wl = client.get(f"/instances/{iid}/worklist").json()
    a_id = wl["ready_activities"][0]
    client.post(f"/instances/{iid}/complete", json={"node_id": a_id})

    # Build a released revision that adds a step ahead of the front.
    revision = client.post(f"/schemas/{sid}/revision", json={}).json()
    rid = revision["id"]
    b_id = next(
        n["id"]
        for n in revision["nodes"].values()
        if n["type"] == "ACTIVITY" and n["label"] == "B"
    )
    client.post(f"/schemas/{rid}/serial-insert", json={"label": "C", "after_node_id": b_id})
    client.post(f"/schemas/{rid}/release")

    check = client.post(
        f"/instances/{iid}/migration-check", json={"target_schema_id": rid}
    )
    assert check.status_code == 200
    assert check.json()["migratable"] is True

    resp = client.post(f"/instances/{iid}/migrate", json={"target_schema_id": rid})
    assert resp.status_code == 200
    migrated = resp.json()
    assert migrated["schema_id"] == rid
    assert migrated["schema_version"] == 2


def test_migration_rewiring_returns_422() -> None:
    sid = _released_two_step("MigrationBlock")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    wl = client.get(f"/instances/{iid}/worklist").json()
    a_id = wl["ready_activities"][0]
    client.post(f"/instances/{iid}/complete", json={"node_id": a_id})

    revision = client.post(f"/schemas/{sid}/revision", json={}).json()
    rid = revision["id"]
    # Insert after the already-completed A -> rewires a completed node (M3).
    client.post(f"/schemas/{rid}/serial-insert", json={"label": "C", "after_node_id": a_id})
    client.post(f"/schemas/{rid}/release")

    resp = client.post(f"/instances/{iid}/migrate", json={"target_schema_id": rid})
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "M3" in rules


def test_activity_template_binding_via_api() -> None:
    sid = client.post("/schemas", json={"name": "RepoApi"}).json()["id"]
    node = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Erfassen", "after_node_id": "start"},
    ).json()
    act_id = next(n["id"] for n in node["nodes"].values() if n["label"] == "Erfassen")
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "betrag", "data_type": "FLOAT", "element_id": "betrag"},
    )
    resp = client.post(
        f"/schemas/{sid}/activity-templates",
        json={
            "name": "Pruefen",
            "executor": "SERVICE",
            "inputs": [{"name": "wert", "data_type": "FLOAT"}],
            "template_id": "t1",
        },
    )
    assert resp.status_code == 200
    resp = client.post(
        f"/schemas/{sid}/service",
        json={
            "node_id": act_id,
            "name": "Pruefen",
            "template_id": "t1",
            "parameter_mapping": {"wert": "betrag"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["service_bindings"][act_id]["automatic"] is True
    assert client.get(f"/schemas/{sid}/validation").json()["correct"] is True


def test_activity_template_type_mismatch_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "RepoApiBad"}).json()["id"]
    node = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Erfassen", "after_node_id": "start"},
    ).json()
    act_id = next(n["id"] for n in node["nodes"].values() if n["label"] == "Erfassen")
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "name", "data_type": "STRING", "element_id": "name"},
    )
    client.post(
        f"/schemas/{sid}/activity-templates",
        json={
            "name": "Pruefen",
            "executor": "SERVICE",
            "inputs": [{"name": "wert", "data_type": "FLOAT"}],
            "template_id": "t1",
        },
    )
    resp = client.post(
        f"/schemas/{sid}/service",
        json={
            "node_id": act_id,
            "name": "Pruefen",
            "template_id": "t1",
            "parameter_mapping": {"wert": "name"},
        },
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "A3" in rules


def test_external_data_binding_via_api() -> None:
    sid = client.post("/schemas", json={"name": "ConnApi"}).json()["id"]
    client.post(
        f"/schemas/{sid}/connectors",
        json={"name": "ERP", "kind": "MS_SQL", "connector_id": "erp"},
    )
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "kunden_nr", "data_type": "STRING", "element_id": "key"},
    )
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "kunde", "data_type": "STRING", "element_id": "kunde"},
    )
    resp = client.post(
        f"/schemas/{sid}/data-elements/kunde/external",
        json={"connector_id": "erp", "entity": "Kunde", "key_element_id": "key"},
    )
    assert resp.status_code == 200
    assert resp.json()["data_elements"]["kunde"]["source"] == "EXTERNAL"
    assert client.get(f"/schemas/{sid}/validation").json()["correct"] is True


def test_external_data_unknown_connector_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "ConnApiBad"}).json()["id"]
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "kunden_nr", "data_type": "STRING", "element_id": "key"},
    )
    client.post(
        f"/schemas/{sid}/data-elements",
        json={"name": "kunde", "data_type": "STRING", "element_id": "kunde"},
    )
    resp = client.post(
        f"/schemas/{sid}/data-elements/kunde/external",
        json={"connector_id": "nope", "entity": "Kunde", "key_element_id": "key"},
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "C1" in rules


def test_bpmn_export_via_api_returns_xml() -> None:
    sid = client.post("/schemas", json={"name": "BpmnExport"}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "S", "after_node_id": "start"})

    resp = client.get(f"/schemas/{sid}/bpmn")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<bpmn:definitions" in resp.text or "definitions" in resp.text


def test_bpmn_import_round_trip_via_api() -> None:
    sid = client.post("/schemas", json={"name": "BpmnImport"}).json()["id"]
    client.post(f"/schemas/{sid}/serial-insert", json={"label": "S", "after_node_id": "start"})
    xml = client.get(f"/schemas/{sid}/bpmn").text

    resp = client.post("/bpmn-import", json={"xml": xml, "name": "Reimport"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Reimport"


def test_bpmn_import_malformed_returns_422() -> None:
    resp = client.post("/bpmn-import", json={"xml": "<definitions>kaputt"})
    assert resp.status_code == 422
    assert "message" in resp.json()["detail"]


def test_cors_header_present_for_browser_client() -> None:
    resp = client.get("/health", headers={"Origin": "http://localhost:5500"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def _released_task_schema(name: str) -> tuple[str, str]:
    """Released schema with one activity bound to role 'sb' (agent a1)."""
    sid = client.post("/schemas", json={"name": name}).json()["id"]
    schema = client.post(
        f"/schemas/{sid}/serial-insert",
        json={"label": "Bearbeiten", "after_node_id": "start"},
    ).json()
    act_id = next(n["id"] for n in schema["nodes"].values() if n["label"] == "Bearbeiten")
    client.post(f"/schemas/{sid}/roles", json={"name": "Sachbearbeiter", "role_id": "sb"})
    client.post(
        f"/schemas/{sid}/agents",
        json={"name": "Erika", "role_ids": ["sb"], "agent_id": "a1"},
    )
    client.post(
        f"/schemas/{sid}/staff-rule",
        json={"node_id": act_id, "rule": {"kind": "ROLE", "ref": "sb"}},
    )
    client.post(f"/schemas/{sid}/release")
    return sid, act_id


def test_agent_tasks_via_api() -> None:
    sid, act_id = _released_task_schema("AufgabenApi")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    resp = client.get("/agents/a1/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert any(t["instance_id"] == iid and t["node_id"] == act_id for t in tasks)

    resp_inst = client.get(f"/instances/{iid}/tasks")
    assert resp_inst.status_code == 200
    assert any(t["node_id"] == act_id for t in resp_inst.json())


def test_complete_with_ineligible_agent_returns_409() -> None:
    sid, act_id = _released_task_schema("AufgabenApiBlock")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    resp = client.post(
        f"/instances/{iid}/complete",
        json={"node_id": act_id, "agent_id": "ghost"},
    )
    assert resp.status_code == 409
    assert "message" in resp.json()["detail"]


def test_complete_with_eligible_agent_records_performer() -> None:
    sid, act_id = _released_task_schema("AufgabenApiOk")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    resp = client.post(
        f"/instances/{iid}/complete",
        json={"node_id": act_id, "agent_id": "a1"},
    )
    assert resp.status_code == 200
    assert resp.json()["performed_by"][act_id] == "a1"


def test_set_org_unit_manager_via_api() -> None:
    sid = client.post("/schemas", json={"name": "ManagerApi"}).json()["id"]
    client.post(f"/schemas/{sid}/org-units", json={"name": "Einkauf", "org_unit_id": "ek"})
    client.post(f"/schemas/{sid}/agents", json={"name": "Chef", "agent_id": "a1"})
    resp = client.post(
        f"/schemas/{sid}/org-units/ek/manager", json={"manager_id": "a1"}
    )
    assert resp.status_code == 200
    assert resp.json()["org_model"]["org_units"]["ek"]["manager_id"] == "a1"


def test_set_org_unit_manager_unknown_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "ManagerApiBad"}).json()["id"]
    client.post(f"/schemas/{sid}/org-units", json={"name": "Einkauf", "org_unit_id": "ek"})
    resp = client.post(
        f"/schemas/{sid}/org-units/ek/manager", json={"manager_id": "ghost"}
    )
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "Z1" in rules


def test_set_org_unit_parent_via_api() -> None:
    sid = client.post("/schemas", json={"name": "ParentApi"}).json()["id"]
    client.post(f"/schemas/{sid}/org-units", json={"name": "Bereich", "org_unit_id": "br"})
    client.post(f"/schemas/{sid}/org-units", json={"name": "Team", "org_unit_id": "tm"})
    resp = client.post(f"/schemas/{sid}/org-units/tm/parent", json={"parent_id": "br"})
    assert resp.status_code == 200
    assert resp.json()["org_model"]["org_units"]["tm"]["parent_id"] == "br"


def test_set_org_unit_parent_cycle_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "ParentApiBad"}).json()["id"]
    client.post(f"/schemas/{sid}/org-units", json={"name": "Bereich", "org_unit_id": "br"})
    client.post(
        f"/schemas/{sid}/org-units",
        json={"name": "Team", "parent_id": "br", "org_unit_id": "tm"},
    )
    resp = client.post(f"/schemas/{sid}/org-units/br/parent", json={"parent_id": "tm"})
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "OP" in rules


def test_set_agent_deputy_via_api() -> None:
    sid = client.post("/schemas", json={"name": "DeputyApi"}).json()["id"]
    client.post(f"/schemas/{sid}/agents", json={"name": "Erika", "agent_id": "a1"})
    client.post(f"/schemas/{sid}/agents", json={"name": "Vertreter", "agent_id": "a2"})
    resp = client.post(f"/schemas/{sid}/agents/a1/deputy", json={"deputy_id": "a2"})
    assert resp.status_code == 200
    assert resp.json()["org_model"]["agents"]["a1"]["deputy_id"] == "a2"


def test_set_agent_self_deputy_returns_422() -> None:
    sid = client.post("/schemas", json={"name": "DeputyApiBad"}).json()["id"]
    client.post(f"/schemas/{sid}/agents", json={"name": "Erika", "agent_id": "a1"})
    resp = client.post(f"/schemas/{sid}/agents/a1/deputy", json={"deputy_id": "a1"})
    assert resp.status_code == 422
    rules = {f["rule"] for f in resp.json()["detail"]["findings"]}
    assert "Z1" in rules


def test_instance_audit_records_lifecycle_events() -> None:
    sid = _released_two_step("AuditLauf")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]

    # Drive the instance to completion.
    while True:
        wl = client.get(f"/instances/{iid}/worklist").json()
        if wl["state"] == "COMPLETED":
            break
        node_id = wl["ready_activities"][0]
        client.post(f"/instances/{iid}/complete", json={"node_id": node_id})

    resp = client.get(f"/instances/{iid}/audit")
    assert resp.status_code == 200
    events = resp.json()
    types = [e["event_type"] for e in events]
    assert types[0] == "INSTANCE_CREATED"
    assert types[-1] == "INSTANCE_COMPLETED"
    assert "ACTIVITY_COMPLETED" in types
    # Events are scoped to the instance and chronologically ordered.
    assert all(e["instance_id"] == iid for e in events)
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)


def test_instance_audit_unknown_instance_returns_404() -> None:
    resp = client.get("/instances/nope/audit")
    assert resp.status_code == 404


def test_complete_with_agent_records_performer_in_audit() -> None:
    sid, act_id = _released_task_schema("AuditBearbeiter")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]
    client.post(f"/instances/{iid}/complete", json={"node_id": act_id, "agent_id": "a1"})

    events = client.get(f"/instances/{iid}/audit").json()
    completed = [e for e in events if e["event_type"] == "ACTIVITY_COMPLETED"]
    assert any(e["node_id"] == act_id and e["agent_id"] == "a1" for e in completed)


def test_monitoring_kpis_via_api() -> None:
    sid = _released_two_step("KpiLauf")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]
    while True:
        wl = client.get(f"/instances/{iid}/worklist").json()
        if wl["state"] == "COMPLETED":
            break
        client.post(f"/instances/{iid}/complete", json={"node_id": wl["ready_activities"][0]})

    resp = client.get("/monitoring/kpis", params={"schema_id": sid})
    assert resp.status_code == 200
    report = resp.json()
    assert report["schema_id"] == sid
    assert report["total_instances"] >= 1
    assert report["completed"] >= 1
    assert any(s["completed"] >= 1 for s in report["activity_stats"])


def test_monitoring_process_map_via_api() -> None:
    sid = _released_two_step("MapLauf")
    iid = client.post(f"/schemas/{sid}/instances").json()["id"]
    while True:
        wl = client.get(f"/instances/{iid}/worklist").json()
        if wl["state"] == "COMPLETED":
            break
        client.post(f"/instances/{iid}/complete", json={"node_id": wl["ready_activities"][0]})

    resp = client.get("/monitoring/process-map", params={"schema_id": sid})
    assert resp.status_code == 200
    pmap = resp.json()
    assert pmap["schema_id"] == sid
    # A -> B was completed in order, so a directly-follows edge must exist.
    assert any(e["frequency"] >= 1 for e in pmap["edges"])










