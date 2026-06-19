# SPDX-License-Identifier: BUSL-1.1
"""Data-flow correctness tests (rules D1-D4, Section 3.2)."""

from __future__ import annotations

import pytest

from procworks import (
    add_data_element,
    conditional_insert,
    connect_data,
    create_empty_schema,
    parallel_insert,
    serial_insert,
    validate,
)
from procworks.model import AccessMode, DataType
from procworks.validator import CorrectnessError


def _activity_ids(schema, label):
    return [n.id for n in schema.nodes.values() if n.label == label]


def test_add_data_element_and_write_then_read_is_correct():
    schema = create_empty_schema("Datenfluss", schema_id="d1ok")
    schema = serial_insert(schema, "Betrag erfassen", after_node_id="start")
    writer = _activity_ids(schema, "Betrag erfassen")[0]
    schema = serial_insert(schema, "Betrag pruefen", after_node_id=writer)
    reader = _activity_ids(schema, "Betrag pruefen")[0]

    schema = add_data_element(schema, "betrag", DataType.FLOAT, element_id="betrag")
    schema = connect_data(schema, writer, "betrag", AccessMode.WRITE)
    schema = connect_data(schema, reader, "betrag", AccessMode.READ)

    assert validate(schema) == []


def test_d1_rejects_read_before_write():
    schema = create_empty_schema("Datenfluss", schema_id="d1bad")
    schema = serial_insert(schema, "Erste", after_node_id="start")
    first = _activity_ids(schema, "Erste")[0]
    schema = serial_insert(schema, "Zweite", after_node_id=first)
    second = _activity_ids(schema, "Zweite")[0]
    schema = add_data_element(schema, "x", DataType.INTEGER, element_id="x")

    # The earlier activity reads, the later one writes -> read before write.
    schema = connect_data(schema, second, "x", AccessMode.WRITE)
    with pytest.raises(CorrectnessError) as exc:
        connect_data(schema, first, "x", AccessMode.READ)
    assert any(f.rule == "D1" for f in exc.value.findings)


def test_d1_write_only_in_one_xor_branch_is_rejected_after_join():
    schema = create_empty_schema("XOR", schema_id="d1xor")
    schema = conditional_insert(
        schema,
        [("a > 0", "Zweig A"), ("a <= 0", "Zweig B")],
        after_node_id="start",
    )
    branch_a = _activity_ids(schema, "Zweig A")[0]
    # Insert an activity after the XOR-join (between join and end).
    join_id = next(
        e.target for e in schema.outgoing(branch_a)
    )  # branch A -> join
    schema = serial_insert(schema, "Nachgelagert", after_node_id=join_id)
    after_join = _activity_ids(schema, "Nachgelagert")[0]

    schema = add_data_element(schema, "a", DataType.INTEGER, element_id="a")
    schema = connect_data(schema, branch_a, "a", AccessMode.WRITE)

    # Reading after the join is not guaranteed: branch B did not write 'a'.
    with pytest.raises(CorrectnessError) as exc:
        connect_data(schema, after_join, "a", AccessMode.READ)
    assert any(f.rule == "D1" for f in exc.value.findings)


def test_d1_write_in_all_xor_branches_supplies_after_join():
    schema = create_empty_schema("XOR", schema_id="d1xorok")
    schema = conditional_insert(
        schema,
        [("a > 0", "Zweig A"), ("a <= 0", "Zweig B")],
        after_node_id="start",
    )
    branch_a = _activity_ids(schema, "Zweig A")[0]
    branch_b = _activity_ids(schema, "Zweig B")[0]
    join_id = next(e.target for e in schema.outgoing(branch_a))
    schema = serial_insert(schema, "Nachgelagert", after_node_id=join_id)
    after_join = _activity_ids(schema, "Nachgelagert")[0]

    schema = add_data_element(schema, "a", DataType.INTEGER, element_id="a")
    schema = connect_data(schema, branch_a, "a", AccessMode.WRITE)
    schema = connect_data(schema, branch_b, "a", AccessMode.WRITE)
    # Now 'a' is written on every path -> read is allowed.
    schema = connect_data(schema, after_join, "a", AccessMode.READ)

    assert validate(schema) == []


def test_d2_rejects_concurrent_writes_in_and_branches():
    schema = create_empty_schema("AND", schema_id="d2bad")
    schema = parallel_insert(schema, ["Zweig 1", "Zweig 2"], after_node_id="start")
    b1 = _activity_ids(schema, "Zweig 1")[0]
    b2 = _activity_ids(schema, "Zweig 2")[0]
    schema = add_data_element(schema, "summe", DataType.FLOAT, element_id="summe")
    schema = connect_data(schema, b1, "summe", AccessMode.WRITE)

    with pytest.raises(CorrectnessError) as exc:
        connect_data(schema, b2, "summe", AccessMode.WRITE)
    assert any(f.rule == "D2" for f in exc.value.findings)


def test_d3_rejects_type_mismatch():
    schema = create_empty_schema("Typen", schema_id="d3bad")
    schema = serial_insert(schema, "Schreiben", after_node_id="start")
    writer = _activity_ids(schema, "Schreiben")[0]
    schema = add_data_element(schema, "flag", DataType.BOOLEAN, element_id="flag")

    with pytest.raises(CorrectnessError) as exc:
        connect_data(
            schema, writer, "flag", AccessMode.WRITE, param_type=DataType.INTEGER
        )
    assert any(f.rule == "D3" for f in exc.value.findings)


def test_d4_rejects_data_access_on_non_activity():
    schema = create_empty_schema("D4", schema_id="d4bad")
    schema = add_data_element(schema, "x", DataType.STRING, element_id="x")
    # 'start' is a START node, not an ACTIVITY -> operation precondition fails.
    with pytest.raises(CorrectnessError) as exc:
        connect_data(schema, "start", "x", AccessMode.READ)
    assert any(f.rule in {"OP", "D4"} for f in exc.value.findings)


def test_connect_data_requires_existing_element():
    schema = create_empty_schema("D4", schema_id="d4missing")
    schema = serial_insert(schema, "A", after_node_id="start")
    act = _activity_ids(schema, "A")[0]
    with pytest.raises(CorrectnessError):
        connect_data(schema, act, "does_not_exist", AccessMode.READ)


def test_add_data_element_rejects_duplicate_id():
    schema = create_empty_schema("Dup", schema_id="dup")
    schema = add_data_element(schema, "x", DataType.INTEGER, element_id="x")
    with pytest.raises(CorrectnessError):
        add_data_element(schema, "x2", DataType.INTEGER, element_id="x")


def test_optional_read_does_not_require_supply():
    schema = create_empty_schema("Optional", schema_id="opt")
    schema = serial_insert(schema, "A", after_node_id="start")
    act = _activity_ids(schema, "A")[0]
    schema = add_data_element(schema, "hint", DataType.STRING, element_id="hint")
    # mandatory=False -> D1 does not require a prior write.
    schema = connect_data(schema, act, "hint", AccessMode.READ, mandatory=False)
    assert validate(schema) == []
