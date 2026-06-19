# SPDX-License-Identifier: BUSL-1.1
"""Tests for the composition rules H1-H4 (sub-processes) and F1-F3 (follow-ups).

A sub-process or follow-up may only reference a RELEASED target with a
type-conformant mapping, and the sub-process hierarchy must stay acyclic.
These checks need a resolver that looks other schemas up.
"""

from __future__ import annotations

import pytest

from procworks import (
    add_data_element,
    create_empty_schema,
    insert_subprocess,
    link_follow_up,
    release,
    serial_insert,
    validate,
)
from procworks.model import DataType, FollowUpTrigger, NodeType, ProcessSchema
from procworks.operations import CorrectnessError


def _resolver_for(*schemas: ProcessSchema):
    by_id = {s.id: s for s in schemas}

    def resolve(schema_id: str, version: int | None) -> ProcessSchema | None:
        schema = by_id.get(schema_id)
        if schema is None:
            return None
        if version is not None and schema.version != version:
            return None
        return schema

    return resolve


def _released_target() -> ProcessSchema:
    sub = create_empty_schema("Sub", schema_id="sub_target")
    sub = serial_insert(sub, "Pruefen", after_node_id="start")
    sub = add_data_element(sub, "betrag", DataType.FLOAT, element_id="betrag")
    return release(sub)


def test_insert_subprocess_against_released_target() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(target, parent)
    parent = insert_subprocess(
        parent, "start", "sub_target", 1, label="Teilprozess", resolver=resolver
    )
    assert validate(parent, resolver) == []
    assert sum(1 for n in parent.nodes.values() if n.type is NodeType.SUBPROCESS) == 1


def test_subprocess_target_must_be_released() -> None:
    draft = create_empty_schema("Entwurf", schema_id="draft_target")
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(draft, parent)
    with pytest.raises(CorrectnessError) as exc:
        insert_subprocess(parent, "start", "draft_target", 1, resolver=resolver)
    assert any(f.rule == "H1" for f in exc.value.findings)


def test_subprocess_unknown_target_is_h1() -> None:
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(parent)
    with pytest.raises(CorrectnessError) as exc:
        insert_subprocess(parent, "start", "ghost", 1, resolver=resolver)
    assert any(f.rule == "H1" for f in exc.value.findings)


def test_subprocess_type_mismatch_is_h2() -> None:
    target = _released_target()  # betrag: FLOAT
    parent = create_empty_schema("Haupt", schema_id="parent")
    parent = add_data_element(parent, "menge", DataType.INTEGER, element_id="menge")
    resolver = _resolver_for(target, parent)
    with pytest.raises(CorrectnessError) as exc:
        insert_subprocess(
            parent,
            "start",
            "sub_target",
            1,
            input_mapping={"betrag": "menge"},  # FLOAT <- INTEGER
            resolver=resolver,
        )
    assert any(f.rule == "H2" for f in exc.value.findings)


def test_subprocess_type_conformant_mapping_ok() -> None:
    target = _released_target()  # betrag: FLOAT
    parent = create_empty_schema("Haupt", schema_id="parent")
    parent = add_data_element(parent, "summe", DataType.FLOAT, element_id="summe")
    resolver = _resolver_for(target, parent)
    parent = insert_subprocess(
        parent,
        "start",
        "sub_target",
        1,
        input_mapping={"betrag": "summe"},  # FLOAT <- FLOAT
        resolver=resolver,
    )
    assert validate(parent, resolver) == []


def test_self_reference_is_cyclic_h3() -> None:
    # A released schema that we pretend references itself via the resolver.
    parent = create_empty_schema("Selbst", schema_id="self")
    resolver = _resolver_for(parent)
    with pytest.raises(CorrectnessError) as exc:
        insert_subprocess(parent, "start", "self", 1, resolver=resolver)
    # self target is ENTWURF (H1) and cyclic (H3)
    assert any(f.rule == "H3" for f in exc.value.findings)


def test_follow_up_against_released_target() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(target, parent)
    parent = link_follow_up(parent, "sub_target", target_version=1, resolver=resolver)
    assert validate(parent, resolver) == []
    assert len(parent.follow_up_links) == 1


def test_follow_up_unknown_target_is_f1() -> None:
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(parent)
    with pytest.raises(CorrectnessError) as exc:
        link_follow_up(parent, "ghost", resolver=resolver)
    assert any(f.rule == "F1" for f in exc.value.findings)


def test_follow_up_handover_type_mismatch_is_f2() -> None:
    target = _released_target()  # betrag: FLOAT
    parent = create_empty_schema("Haupt", schema_id="parent")
    parent = add_data_element(parent, "anzahl", DataType.INTEGER, element_id="anzahl")
    resolver = _resolver_for(target, parent)
    with pytest.raises(CorrectnessError) as exc:
        link_follow_up(
            parent,
            "sub_target",
            target_version=1,
            handover_mapping={"betrag": "anzahl"},  # FLOAT <- INTEGER
            resolver=resolver,
        )
    assert any(f.rule == "F2" for f in exc.value.findings)


def test_conditional_follow_up_unknown_element_is_f4() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(target, parent)
    with pytest.raises(CorrectnessError) as exc:
        link_follow_up(
            parent,
            "sub_target",
            target_version=1,
            trigger=FollowUpTrigger.CONDITIONAL,
            condition="unbekannt > 0",
            resolver=resolver,
        )
    assert any(f.rule == "F4" for f in exc.value.findings)


def test_conditional_follow_up_without_condition_is_f4() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(target, parent)
    with pytest.raises(CorrectnessError) as exc:
        link_follow_up(
            parent,
            "sub_target",
            target_version=1,
            trigger=FollowUpTrigger.CONDITIONAL,
            resolver=resolver,
        )
    assert any(f.rule == "F4" for f in exc.value.findings)


def test_conditional_follow_up_with_valid_condition_ok() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    parent = add_data_element(parent, "anzahl", DataType.INTEGER, element_id="anzahl")
    resolver = _resolver_for(target, parent)
    parent = link_follow_up(
        parent,
        "sub_target",
        target_version=1,
        trigger=FollowUpTrigger.CONDITIONAL,
        condition="anzahl > 0",
        resolver=resolver,
    )
    assert validate(parent, resolver) == []


def test_release_parent_with_released_subprocess() -> None:
    target = _released_target()
    parent = create_empty_schema("Haupt", schema_id="parent")
    resolver = _resolver_for(target, parent)
    parent = insert_subprocess(parent, "start", "sub_target", 1, resolver=resolver)
    released = release(parent, resolver)
    assert released.lifecycle_state.value == "RELEASED"
