# SPDX-License-Identifier: BUSL-1.1
"""Tests for the Correctness Validator (K1-K3) and change operations.

These tests demonstrate Correctness by Construction:
  * operations always yield a structurally correct schema (happy path),
  * the validator has teeth: it rejects hand-crafted broken schemas,
  * operation preconditions reject illegal calls.
"""

from __future__ import annotations

import pytest

from procworks import (
    conditional_insert,
    create_empty_schema,
    parallel_insert,
    release,
    serial_insert,
    validate,
)
from procworks.model import ControlEdge, LifecycleState, Node, NodeType, ProcessSchema
from procworks.operations import CorrectnessError


def test_empty_schema_is_correct() -> None:
    schema = create_empty_schema("Leer")
    assert validate(schema) == []
    assert schema.start_node().type is NodeType.START
    assert schema.end_node().type is NodeType.END


def test_serial_insert_keeps_schema_correct() -> None:
    schema = create_empty_schema("Seriell")
    schema = serial_insert(schema, "Antrag prüfen", after_node_id="start")
    schema = serial_insert(schema, "Antrag genehmigen", after_node_id="start")
    assert validate(schema) == []
    activities = [n for n in schema.nodes.values() if n.type is NodeType.ACTIVITY]
    assert {a.label for a in activities} == {"Antrag prüfen", "Antrag genehmigen"}


def test_parallel_insert_builds_balanced_and_block() -> None:
    schema = create_empty_schema("Parallel")
    schema = parallel_insert(schema, ["Fachprüfung", "Budgetprüfung"], after_node_id="start")
    assert validate(schema) == []
    assert sum(1 for n in schema.nodes.values() if n.type is NodeType.AND_SPLIT) == 1
    assert sum(1 for n in schema.nodes.values() if n.type is NodeType.AND_JOIN) == 1


def test_conditional_insert_builds_balanced_xor_block() -> None:
    schema = create_empty_schema("Bedingt")
    schema = conditional_insert(
        schema,
        [("betrag > 1000", "Freigabe Leitung"), ("betrag <= 1000", "Freigabe Team")],
        after_node_id="start",
    )
    assert validate(schema) == []
    xor_edges = [e for e in schema.edges if e.condition is not None]
    assert {e.condition for e in xor_edges} == {"betrag > 1000", "betrag <= 1000"}


def test_nested_block_inside_branch() -> None:
    schema = create_empty_schema("Verschachtelt")
    schema = parallel_insert(schema, ["A", "B"], after_node_id="start")
    branch_a = next(n for n in schema.nodes.values() if n.label == "A")
    schema = serial_insert(schema, "A2", after_node_id=branch_a.id)
    assert validate(schema) == []


def test_validator_rejects_dangling_node() -> None:
    schema = create_empty_schema("Defekt")
    schema.nodes["ghost"] = Node(id="ghost", type=NodeType.ACTIVITY, label="verwaist")
    findings = validate(schema)
    rules = {f.rule for f in findings}
    assert "K2" in rules or "K3" in rules


def test_validator_rejects_unbalanced_gateway() -> None:
    # START -> XOR_SPLIT -> (A, B) -> END  without a join => K1 + K2 violations.
    schema = ProcessSchema(
        id="x",
        name="Unbalanciert",
        nodes={
            "start": Node(id="start", type=NodeType.START),
            "xs": Node(id="xs", type=NodeType.XOR_SPLIT),
            "a": Node(id="a", type=NodeType.ACTIVITY, label="A"),
            "b": Node(id="b", type=NodeType.ACTIVITY, label="B"),
            "end": Node(id="end", type=NodeType.END),
        },
        edges=[
            ControlEdge(source="start", target="xs"),
            ControlEdge(source="xs", target="a"),
            ControlEdge(source="xs", target="b"),
            ControlEdge(source="a", target="end"),
            ControlEdge(source="b", target="end"),
        ],
    )
    findings = validate(schema)
    assert any(f.rule == "K1" for f in findings)


def test_serial_insert_after_unknown_node_is_rejected() -> None:
    schema = create_empty_schema("Fehler")
    with pytest.raises(CorrectnessError):
        serial_insert(schema, "X", after_node_id="does-not-exist")


def test_cannot_insert_after_end() -> None:
    schema = create_empty_schema("Fehler")
    with pytest.raises(CorrectnessError):
        serial_insert(schema, "X", after_node_id="end")


def test_parallel_insert_requires_two_branches() -> None:
    schema = create_empty_schema("Fehler")
    with pytest.raises(CorrectnessError):
        parallel_insert(schema, ["nur eine"], after_node_id="start")


def test_release_requires_entwurf_and_marks_released() -> None:
    schema = create_empty_schema("Release")
    schema = serial_insert(schema, "Schritt", after_node_id="start")
    released = release(schema)
    assert released.lifecycle_state is LifecycleState.RELEASED


def test_released_schema_is_not_editable() -> None:
    schema = create_empty_schema("Immutable")
    released = release(schema)
    with pytest.raises(CorrectnessError):
        serial_insert(released, "X", after_node_id="start")
