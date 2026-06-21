# SPDX-License-Identifier: BUSL-1.1
"""Data Access Layer and connector SPI (Section 9, step 12).

EXTERNAL data elements (see ``DataElement.source``) are not stored in the
process instance but resolved against a central database or business
application through a *connector*. The Data Access Layer (DAL) provides a
single, uniform read/write/query interface and routes each access to the
connector a data element is bound to.

Security by design:
  * Credentials/endpoints never live in the schema -- the connector instance
    holds them and is registered server-side.
  * The lookup key and write values are always passed as *parameters*
    (``read(entity, key)`` / ``write(entity, key, values)``); they are never
    concatenated into a query string, so there is no injection surface.

The in-memory connector below is the reference implementation used in tests
and demos; real connectors (MS SQL, MySQL, Dynamics 365, SAP) implement the
same ``Connector`` protocol.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

from procworks.model import DataSourceKind, ExternalBinding, ProcessSchema

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

#: A single external record as returned/accepted by a connector.
Record = Mapping[str, object]

#: A single, unqualified SQL identifier (column / unqualified table name).
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: An entity name, optionally schema-qualified (``schema.table``).
_ENTITY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


class DataAccessError(RuntimeError):
    """Raised when an external data access cannot be resolved or executed."""


class Connector(Protocol):
    """The narrow SPI every data connector implements.

    All accesses are parameterized: ``key`` and ``values`` are data, never
    interpolated into a statement.
    """

    def read(self, entity: str, key: object) -> Record:
        """Return the record of ``entity`` identified by ``key``."""
        ...

    def write(self, entity: str, key: object, values: Record) -> None:
        """Insert or update the record of ``entity`` identified by ``key``."""
        ...

    def query(self, entity: str, filters: Record) -> list[Record]:
        """Return all records of ``entity`` matching every key/value in ``filters``."""
        ...


class InMemoryConnector:
    """A simple dict-backed connector for tests and local demos."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[object, dict[str, object]]] = {}

    def read(self, entity: str, key: object) -> Record:
        try:
            return dict(self._rows[entity][key])
        except KeyError as exc:
            raise DataAccessError(
                f"no record '{key}' in entity '{entity}'"
            ) from exc

    def write(self, entity: str, key: object, values: Record) -> None:
        self._rows.setdefault(entity, {})[key] = dict(values)

    def query(self, entity: str, filters: Record) -> list[Record]:
        rows = self._rows.get(entity, {})
        return [
            dict(row)
            for row in rows.values()
            if all(row.get(field) == value for field, value in filters.items())
        ]


def _safe_identifier(name: str) -> str:
    """Return ``name`` if it is a single safe SQL identifier, else raise.

    Table/column names cannot be passed as bind parameters, so they are the only
    injection surface. Every identifier that reaches a statement is whitelisted
    against a strict pattern (letters/digits/underscore, no quoting tricks) and
    additionally dialect-quoted before interpolation -- values always travel as
    bound parameters.
    """

    if not _IDENTIFIER.match(name):
        raise DataAccessError(f"unsafe SQL identifier '{name}'")
    return name


def _safe_entity(name: str) -> str:
    """Return ``name`` if it is a safe (optionally schema-qualified) entity."""

    if not _ENTITY.match(name):
        raise DataAccessError(f"unsafe SQL entity '{name}'")
    return name


class SqlAlchemyConnector:
    """A real, parameterized SQL connector built on SQLAlchemy Core.

    Talks to any SQLAlchemy-supported dialect (PostgreSQL, MySQL/MariaDB,
    Microsoft SQL Server, SQLite, ...). The engine carries the credentials and
    is built server-side from the connection registry -- never from the schema.

    Security by design:
      * Lookup keys and written values are always **bound parameters**; they are
        never concatenated into a statement (no injection surface).
      * Table/column **identifiers** are whitelisted against a strict pattern and
        dialect-quoted, so a crafted entity/column name cannot break out either.

    ``key_column`` is the primary-key column used to address a record; per-entity
    overrides may be supplied via ``entity_key_columns``.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        key_column: str = "id",
        entity_key_columns: Mapping[str, str] | None = None,
    ) -> None:
        self._engine = engine
        self._key_column = key_column
        self._entity_key_columns = dict(entity_key_columns or {})

    def _key_col(self, entity: str) -> str:
        return self._entity_key_columns.get(entity, self._key_column)

    def _quote_ident(self, name: str) -> str:
        return self._engine.dialect.identifier_preparer.quote(_safe_identifier(name))

    def _quote_entity(self, entity: str) -> str:
        _safe_entity(entity)
        return ".".join(self._quote_ident(part) for part in entity.split("."))

    def read(self, entity: str, key: object) -> Record:
        from sqlalchemy import text

        table = self._quote_entity(entity)
        key_col = self._quote_ident(self._key_col(entity))
        stmt = text(f"SELECT * FROM {table} WHERE {key_col} = :key")
        with self._engine.connect() as conn:
            row = conn.execute(stmt, {"key": key}).mappings().first()
        if row is None:
            raise DataAccessError(f"no record '{key}' in entity '{entity}'")
        return dict(row)

    def write(self, entity: str, key: object, values: Record) -> None:
        from sqlalchemy import text

        table = self._quote_entity(entity)
        key_name = self._key_col(entity)
        key_col = self._quote_ident(key_name)
        cols = [c for c in values if c != key_name]
        params: dict[str, object] = {f"v_{c}": values[c] for c in cols}
        params["key"] = key
        with self._engine.begin() as conn:
            exists = conn.execute(
                text(f"SELECT 1 FROM {table} WHERE {key_col} = :key"), {"key": key}
            ).first()
            if exists is not None:
                if cols:
                    assignments = ", ".join(
                        f"{self._quote_ident(c)} = :v_{c}" for c in cols
                    )
                    conn.execute(
                        text(f"UPDATE {table} SET {assignments} WHERE {key_col} = :key"),
                        params,
                    )
                return
            insert_cols = ", ".join([key_col, *(self._quote_ident(c) for c in cols)])
            placeholders = ", ".join([":key", *(f":v_{c}" for c in cols)])
            conn.execute(
                text(f"INSERT INTO {table} ({insert_cols}) VALUES ({placeholders})"),
                params,
            )

    def query(self, entity: str, filters: Record) -> list[Record]:
        from sqlalchemy import text

        table = self._quote_entity(entity)
        params: dict[str, object] = {}
        where = ""
        if filters:
            clauses = []
            for i, (field, value) in enumerate(filters.items()):
                placeholder = f"f{i}"
                clauses.append(f"{self._quote_ident(field)} = :{placeholder}")
                params[placeholder] = value
            where = " WHERE " + " AND ".join(clauses)
        with self._engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {table}{where}"), params).mappings().all()
        return [dict(row) for row in rows]

    def ping(self) -> None:
        """Read-only connection check used by ``/connectors/{id}/test``."""

        from sqlalchemy import text

        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))



class DataAccessLayer:
    """Routes external data accesses of a schema to registered connectors."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector_id: str, connector: Connector) -> None:
        """Make a connector instance available under ``connector_id``."""

        self._connectors[connector_id] = connector

    def connector(self, connector_id: str) -> Connector:
        """Return the registered connector or raise ``DataAccessError``."""

        connector = self._connectors.get(connector_id)
        if connector is None:
            raise DataAccessError(f"connector '{connector_id}' is not registered")
        return connector

    def _binding(self, schema: ProcessSchema, element_id: str) -> ExternalBinding:
        element = schema.data_elements.get(element_id)
        if element is None:
            raise DataAccessError(f"unknown data element '{element_id}'")
        if element.source is not DataSourceKind.EXTERNAL or element.external is None:
            raise DataAccessError(f"data element '{element_id}' is not EXTERNAL")
        return element.external

    def _key(self, binding: ExternalBinding, instance_values: Record) -> object:
        if binding.key_element_id not in instance_values:
            raise DataAccessError(
                f"lookup key '{binding.key_element_id}' is not set in the instance"
            )
        return instance_values[binding.key_element_id]

    def read(
        self, schema: ProcessSchema, instance_values: Record, element_id: str
    ) -> Record:
        """Resolve and read an EXTERNAL element for the given instance values."""

        binding = self._binding(schema, element_id)
        key = self._key(binding, instance_values)
        return self.connector(binding.connector_id).read(binding.entity, key)

    def write(
        self,
        schema: ProcessSchema,
        instance_values: Record,
        element_id: str,
        values: Record,
    ) -> None:
        """Resolve and write an EXTERNAL element for the given instance values."""

        binding = self._binding(schema, element_id)
        key = self._key(binding, instance_values)
        self.connector(binding.connector_id).write(binding.entity, key, values)

    def query(
        self, schema: ProcessSchema, element_id: str, filters: Record
    ) -> list[Record]:
        """Query the entity an EXTERNAL element is bound to."""

        binding = self._binding(schema, element_id)
        return self.connector(binding.connector_id).query(binding.entity, filters)
