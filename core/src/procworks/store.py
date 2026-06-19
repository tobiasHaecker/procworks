"""Schema store interface, in-memory implementation, and a store factory.

The API depends only on the ``SchemaStore`` protocol, so the backing store can
be swapped (in-memory for tests/demo, PostgreSQL for real deployments) without
touching the endpoints.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol

from procworks.model import OrgModel, ProcessInstance, ProcessSchema


class SchemaStore(Protocol):
    """Minimal persistence interface for process schemas."""

    def put(self, schema: ProcessSchema) -> ProcessSchema: ...

    def get(self, schema_id: str) -> ProcessSchema | None: ...

    def list_ids(self) -> list[str]: ...


def make_resolver(
    store: SchemaStore,
) -> Callable[[str, int | None], ProcessSchema | None]:
    """Build a schema resolver for the composition rules (H1-H4, F1-F3).

    Resolves a schema by id and, if a version is pinned, only returns it when
    the stored version matches. With the simplified single-version store this
    is sufficient to enforce the pinned-version semantics.
    """

    def resolve(schema_id: str, version: int | None) -> ProcessSchema | None:
        schema = store.get(schema_id)
        if schema is None:
            return None
        if version is not None and schema.version != version:
            return None
        return schema

    return resolve




class InMemorySchemaStore:
    """A trivial dict-backed store of schemas keyed by id (default for tests)."""

    def __init__(self) -> None:
        self._schemas: dict[str, ProcessSchema] = {}

    def put(self, schema: ProcessSchema) -> ProcessSchema:
        self._schemas[schema.id] = schema
        return schema

    def get(self, schema_id: str) -> ProcessSchema | None:
        return self._schemas.get(schema_id)

    def list_ids(self) -> list[str]:
        return list(self._schemas.keys())


def create_store() -> SchemaStore:
    """Build the store from the environment.

    If ``DATABASE_URL`` is set, use the SQLAlchemy-backed store (tables are
    created on first use for convenience; production should rely on Alembic).
    Otherwise fall back to the in-memory store.
    """

    url = os.environ.get("DATABASE_URL")
    if url:
        # Imported lazily so the in-memory path has no SQLAlchemy import cost.
        from procworks.db import SqlAlchemySchemaStore

        return SqlAlchemySchemaStore(url, create_tables=True)
    return InMemorySchemaStore()


class InstanceStore(Protocol):
    """Minimal persistence interface for process instances."""

    def put(self, instance: ProcessInstance) -> ProcessInstance: ...

    def get(self, instance_id: str) -> ProcessInstance | None: ...

    def list_ids(self) -> list[str]: ...


class InMemoryInstanceStore:
    """A trivial dict-backed store of running instances keyed by id.

    This is the default store without configuration; with ``DATABASE_URL`` set,
    ``create_instance_store`` returns the durable ``SqlAlchemyInstanceStore``
    instead (mirroring the schema store).
    """

    def __init__(self) -> None:
        self._instances: dict[str, ProcessInstance] = {}

    def put(self, instance: ProcessInstance) -> ProcessInstance:
        self._instances[instance.id] = instance
        return instance

    def get(self, instance_id: str) -> ProcessInstance | None:
        return self._instances.get(instance_id)

    def list_ids(self) -> list[str]:
        return list(self._instances.keys())


def create_instance_store() -> InstanceStore:
    """Build the instance store from the environment.

    If ``DATABASE_URL`` is set, use the SQLAlchemy-backed store (durable
    instance persistence; tables are created on first use for convenience,
    production should rely on Alembic). Otherwise fall back to in-memory.
    """

    url = os.environ.get("DATABASE_URL")
    if url:
        from procworks.db import SqlAlchemyInstanceStore

        return SqlAlchemyInstanceStore(url, create_tables=True)
    return InMemoryInstanceStore()


class OrgStore(Protocol):
    """Minimal persistence interface for shared, standalone org models."""

    def put(self, org: OrgModel) -> OrgModel: ...

    def get(self, org_id: str) -> OrgModel | None: ...

    def list_ids(self) -> list[str]: ...


class InMemoryOrgStore:
    """A trivial dict-backed store of shared org models keyed by id."""

    def __init__(self) -> None:
        self._orgs: dict[str, OrgModel] = {}

    def put(self, org: OrgModel) -> OrgModel:
        if org.id is None:
            raise ValueError("a shared org model must have an id before it is stored")
        self._orgs[org.id] = org
        return org

    def get(self, org_id: str) -> OrgModel | None:
        return self._orgs.get(org_id)

    def list_ids(self) -> list[str]:
        return list(self._orgs.keys())


def create_org_store() -> OrgStore:
    """Build the shared-org store from the environment (mirrors the others)."""

    url = os.environ.get("DATABASE_URL")
    if url:
        from procworks.db import SqlAlchemyOrgStore

        return SqlAlchemyOrgStore(url, create_tables=True)
    return InMemoryOrgStore()


def make_org_resolver(store: OrgStore) -> Callable[[str | None], OrgModel | None]:
    """Build a resolver that maps a (possibly absent) org id to its model."""

    def resolve(org_id: str | None) -> OrgModel | None:
        if org_id is None:
            return None
        return store.get(org_id)

    return resolve


def hydrate_org(
    schema: ProcessSchema, org_resolver: Callable[[str | None], OrgModel | None]
) -> ProcessSchema:
    """Fill ``schema.org_model`` from the shared registry when linked.

    A schema that references a shared org model carries only an empty embedded
    ``org_model`` in storage; before any validation / resolution it must be
    *hydrated* with the live shared model. Unlinked schemas are returned
    unchanged. If the referenced model is missing, the (empty) embedded model
    is left in place so validation surfaces the dangling references.
    """

    if schema.org_model_id is None:
        return schema
    org = org_resolver(schema.org_model_id)
    if org is None:
        return schema
    return schema.model_copy(update={"org_model": org.model_copy(deep=True)})


def dehydrate_org(schema: ProcessSchema) -> ProcessSchema:
    """Clear the hydrated org master data before persisting a linked schema.

    Keeps the shared org registry the single source of truth: a linked schema
    is stored with an empty embedded ``org_model`` (only ``org_model_id`` is
    persisted). Unlinked schemas are returned unchanged.
    """

    if schema.org_model_id is None:
        return schema
    return schema.model_copy(update={"org_model": OrgModel()})

