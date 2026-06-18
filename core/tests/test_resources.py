"""Resource / staff-assignment correctness tests (rules Z1-Z4, Section 3.2.1)."""

from __future__ import annotations

import pytest

from procworks import (
    add_agent,
    add_org_unit,
    add_role,
    assign_service,
    assign_staff_rule,
    create_empty_schema,
    parallel_insert,
    serial_insert,
    validate,
)
from procworks.model import StaffRule, StaffRuleKind
from procworks.validator import CorrectnessError


def _activity_ids(schema, label):
    return [n.id for n in schema.nodes.values() if n.label == label]


def _role_rule(role_id: str) -> StaffRule:
    return StaffRule(kind=StaffRuleKind.ROLE, ref=role_id)


def test_role_rule_with_agent_is_correct():
    schema = create_empty_schema("Ressourcen", schema_id="zok")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]

    schema = add_role(schema, "Sachbearbeiter", role_id="sb")
    schema = add_agent(schema, "Erika", role_ids=["sb"], agent_id="a1")
    schema = assign_staff_rule(schema, act, _role_rule("sb"))

    assert validate(schema) == []


def test_z1_rejects_unknown_role():
    schema = create_empty_schema("Z1", schema_id="z1bad")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]
    with pytest.raises(CorrectnessError) as exc:
        assign_staff_rule(schema, act, _role_rule("does_not_exist"))
    assert any(f.rule == "Z1" for f in exc.value.findings)


def test_z2_rejects_role_without_agents():
    schema = create_empty_schema("Z2", schema_id="z2bad")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]
    schema = add_role(schema, "Leerrolle", role_id="leer")
    with pytest.raises(CorrectnessError) as exc:
        assign_staff_rule(schema, act, _role_rule("leer"))
    assert any(f.rule == "Z2" for f in exc.value.findings)


def test_z2_or_of_empty_and_filled_role_is_resolvable():
    schema = create_empty_schema("Z2or", schema_id="z2or")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]
    schema = add_role(schema, "Leer", role_id="leer")
    schema = add_role(schema, "Voll", role_id="voll")
    schema = add_agent(schema, "Max", role_ids=["voll"], agent_id="a1")
    rule = StaffRule(
        kind=StaffRuleKind.OR,
        operands=[_role_rule("leer"), _role_rule("voll")],
    )
    schema = assign_staff_rule(schema, act, rule)
    assert validate(schema) == []


def test_z3_node_performing_agent_requires_prior_node():
    schema = create_empty_schema("Z3", schema_id="z3ok")
    schema = serial_insert(schema, "Erster", after_node_id="start")
    first = _activity_ids(schema, "Erster")[0]
    schema = serial_insert(schema, "Zweiter", after_node_id=first)
    second = _activity_ids(schema, "Zweiter")[0]

    rule = StaffRule(kind=StaffRuleKind.NODE_PERFORMING_AGENT, ref=first)
    schema = assign_staff_rule(schema, second, rule)
    assert validate(schema) == []


def test_z3_rejects_backref_not_guaranteed_before():
    schema = create_empty_schema("Z3bad", schema_id="z3bad")
    schema = parallel_insert(schema, ["Zweig 1", "Zweig 2"], after_node_id="start")
    b1 = _activity_ids(schema, "Zweig 1")[0]
    b2 = _activity_ids(schema, "Zweig 2")[0]
    # b1 and b2 are on parallel branches: b1 is not guaranteed before b2.
    rule = StaffRule(kind=StaffRuleKind.NODE_PERFORMING_AGENT, ref=b1)
    with pytest.raises(CorrectnessError) as exc:
        assign_staff_rule(schema, b2, rule)
    assert any(f.rule == "Z3" for f in exc.value.findings)


def test_z4_automatic_service_rejects_staff_rule():
    schema = create_empty_schema("Z4", schema_id="z4bad")
    schema = serial_insert(schema, "Auto", after_node_id="start")
    act = _activity_ids(schema, "Auto")[0]
    schema = add_role(schema, "Rolle", role_id="r")
    schema = add_agent(schema, "Agent", role_ids=["r"], agent_id="a1")
    schema = assign_service(schema, act, "Auto-Dienst", automatic=True)
    with pytest.raises(CorrectnessError) as exc:
        assign_staff_rule(schema, act, _role_rule("r"))
    assert any(f.rule == "Z4" for f in exc.value.findings)


def test_interactive_service_with_staff_rule_is_correct():
    schema = create_empty_schema("Z4ok", schema_id="z4ok")
    schema = serial_insert(schema, "Interaktiv", after_node_id="start")
    act = _activity_ids(schema, "Interaktiv")[0]
    schema = add_role(schema, "Rolle", role_id="r")
    schema = add_agent(schema, "Agent", role_ids=["r"], agent_id="a1")
    schema = assign_service(schema, act, "Formular", automatic=False)
    schema = assign_staff_rule(schema, act, _role_rule("r"))
    assert validate(schema) == []


def test_org_unit_recursive_includes_sub_units():
    schema = create_empty_schema("Units", schema_id="units")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]
    schema = add_org_unit(schema, "Bereich", org_unit_id="bereich")
    schema = add_org_unit(schema, "Team", parent_id="bereich", org_unit_id="team")
    schema = add_agent(schema, "Teammitglied", org_unit_id="team", agent_id="a1")

    # Non-recursive on the parent unit finds no direct member -> Z2.
    with pytest.raises(CorrectnessError):
        assign_staff_rule(
            schema, act, StaffRule(kind=StaffRuleKind.ORG_UNIT, ref="bereich")
        )

    # Recursive includes the sub-unit's agent -> resolvable.
    schema = assign_staff_rule(
        schema,
        act,
        StaffRule(kind=StaffRuleKind.ORG_UNIT, ref="bereich", recursive=True),
    )
    assert validate(schema) == []


def test_add_agent_rejects_unknown_role():
    schema = create_empty_schema("Agents", schema_id="agbad")
    with pytest.raises(CorrectnessError):
        add_agent(schema, "Niemand", role_ids=["ghost"], agent_id="a1")


def test_except_rule_upper_bound_resolvable():
    schema = create_empty_schema("Except", schema_id="except")
    schema = serial_insert(schema, "Bearbeiten", after_node_id="start")
    act = _activity_ids(schema, "Bearbeiten")[0]
    schema = add_role(schema, "Alle", role_id="alle")
    schema = add_role(schema, "Gesperrt", role_id="gesperrt")
    schema = add_agent(schema, "A", role_ids=["alle"], agent_id="a1")
    schema = add_agent(schema, "B", role_ids=["alle", "gesperrt"], agent_id="a2")
    rule = StaffRule(
        kind=StaffRuleKind.EXCEPT,
        operands=[_role_rule("alle"), _role_rule("gesperrt")],
    )
    schema = assign_staff_rule(schema, act, rule)
    assert validate(schema) == []
