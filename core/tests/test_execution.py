# SPDX-License-Identifier: BUSL-1.1
"""Tests for the Execution Engine (roadmap step 8).

These verify the runtime marking semantics: a RELEASED schema is instantiated,
activities become ready in the right order, parallel (AND) branches run
concurrently, XOR branch selection skips the unchosen branch, and a finished
instance ends with every node COMPLETED or SKIPPED.
"""

from __future__ import annotations

import pytest

from procworks import (
    complete_activity,
    conditional_insert,
    create_empty_schema,
    decide_branch,
    instantiate,
    parallel_insert,
    pending_decisions,
    release,
    serial_insert,
    start_activity,
    worklist,
)
from procworks.execution import ExecutionError
from procworks.model import InstanceState, NodeState, NodeType


def _released_serial() -> object:
    schema = create_empty_schema("Seriell")
    schema = serial_insert(schema, "B", after_node_id="start")
    schema = serial_insert(schema, "A", after_node_id="start")
    return release(schema)


def test_instantiate_requires_released() -> None:
    schema = create_empty_schema("Entwurf")
    with pytest.raises(ExecutionError):
        instantiate(schema)


def test_serial_run_completes() -> None:
    schema = _released_serial()
    instance = instantiate(schema)
    # exactly one activity ready at a time (A then B)
    ready = worklist(instance, schema)
    assert len(ready) == 1
    first = ready[0]
    instance = start_activity(instance, schema, first)
    assert instance.node_states[first] is NodeState.RUNNING
    instance = complete_activity(instance, schema, first)

    ready = worklist(instance, schema)
    assert len(ready) == 1
    second = ready[0]
    assert second != first
    instance = complete_activity(instance, schema, second)

    assert instance.state is InstanceState.COMPLETED
    assert all(
        st in (NodeState.COMPLETED, NodeState.SKIPPED)
        for st in instance.node_states.values()
    )


def test_parallel_branches_are_concurrently_ready() -> None:
    schema = create_empty_schema("Parallel")
    schema = parallel_insert(schema, ["L", "R"], after_node_id="start")
    schema = release(schema)
    instance = instantiate(schema)

    ready = worklist(instance, schema)
    assert len(ready) == 2  # both AND branches active at once

    for node_id in list(ready):
        instance = complete_activity(instance, schema, node_id)

    assert instance.state is InstanceState.COMPLETED
    assert all(
        st is NodeState.COMPLETED
        for nid, st in instance.node_states.items()
        if schema.nodes[nid].type is NodeType.ACTIVITY
    )


def test_xor_decision_skips_unchosen_branch() -> None:
    schema = create_empty_schema("Bedingt")
    schema = conditional_insert(
        schema,
        [("betrag > 1000", "Leitung"), ("betrag <= 1000", "Team")],
        after_node_id="start",
    )
    schema = release(schema)
    instance = instantiate(schema)

    # the run is paused at the XOR split waiting for a decision
    assert worklist(instance, schema) == []
    pending = pending_decisions(instance, schema)
    assert len(pending) == 1
    split_id = pending[0]

    chosen = next(n for n in schema.nodes.values() if n.label == "Leitung")
    not_chosen = next(n for n in schema.nodes.values() if n.label == "Team")
    instance = decide_branch(instance, schema, split_id, chosen.id)

    ready = worklist(instance, schema)
    assert ready == [chosen.id]
    assert instance.node_states[not_chosen.id] is NodeState.SKIPPED

    instance = complete_activity(instance, schema, chosen.id)
    assert instance.state is InstanceState.COMPLETED
    assert instance.node_states[chosen.id] is NodeState.COMPLETED
    assert instance.node_states[not_chosen.id] is NodeState.SKIPPED


def test_complete_with_data_stores_values() -> None:
    schema = _released_serial()
    instance = instantiate(schema)
    first = worklist(instance, schema)[0]
    instance = complete_activity(instance, schema, first, {"betrag": 1500})
    assert instance.data_values["betrag"] == 1500


def test_start_non_activated_activity_fails() -> None:
    schema = _released_serial()
    instance = instantiate(schema)
    not_ready = next(
        nid
        for nid, st in instance.node_states.items()
        if st is NodeState.NOT_ACTIVATED
        and schema.nodes[nid].type is NodeType.ACTIVITY
    )
    with pytest.raises(ExecutionError):
        start_activity(instance, schema, not_ready)


def test_decide_unknown_branch_fails() -> None:
    schema = create_empty_schema("Bedingt")
    schema = conditional_insert(
        schema,
        [("a", "L"), ("b", "R")],
        after_node_id="start",
    )
    schema = release(schema)
    instance = instantiate(schema)
    split_id = pending_decisions(instance, schema)[0]
    with pytest.raises(ExecutionError):
        decide_branch(instance, schema, split_id, "does_not_exist")
